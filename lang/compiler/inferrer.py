import string
from dataclasses import dataclass
from itertools import count
from typing import Self, assert_never

from lang.exceptions import InferrerError
from lang.lang_type import (
    FunctionLanguageType,
    InferableLanguageType,
    LanguageType,
    LanguageTypeVar,
    PrimitiveLanguageType,
    SubstitutionMap,
    UnificationError,
)
from lang.parser import ParserResult
from lang.parser.qualname import (
    BaseConstQualName,
    BuiltinQualName,
    DefinitionQualName,
    GenericBuiltinQualName,
    GenericBuiltinSymbol,
    LanguageTypeVarEmitter,
    ProjectionQualName,
    QualName,
    TreePath,
    UsageQualName,
)
from lang.parser.qualname_assign import FinalToken, QualifiedToken, VirtualToken
from lang.parser.s_expr import (
    SExprCall,
    SExprDefun,
    SExprFile,
    SExprIf,
    SExprLambda,
    SExprProgn,
    SExprSetq,
    SExprWhile,
)
from lang.parser.token_storage import TokenStorage, TokenView


@dataclass
class InferableQualName:
    qualname: QualName
    token: FinalToken
    lang_type: LanguageType | InferableLanguageType


@dataclass
class InferredQualName:
    """Квалифицированное имя с полностью выведенным конкретным типом."""

    qualname: (
        BuiltinQualName
        | UsageQualName
        | DefinitionQualName
        | ProjectionQualName
        | BaseConstQualName
    )
    token: FinalToken
    lang_type: LanguageType


@dataclass
class InferableUnificationResult:
    _did_change: bool

    @property
    def was_unified(self):
        return self._did_change

    @staticmethod
    def changed():
        return InferableUnificationResult(_did_change=True)

    @staticmethod
    def empty():
        return InferableUnificationResult(_did_change=False)

    def __or__(self: Self, value: Self) -> Self:
        self._did_change |= value._did_change
        return self


def unify(
    u1: InferableLanguageType | InferableQualName,
    u2: InferableLanguageType | InferableQualName,
    subm: SubstitutionMap,
) -> InferableUnificationResult:
    t1 = u1.lang_type if isinstance(u1, InferableQualName) else u1
    t2 = u2.lang_type if isinstance(u2, InferableQualName) else u2

    t1 = t1.deref(subm)
    t2 = t2.deref(subm)

    if t1.is_same(t2, subm):
        return InferableUnificationResult.empty()

    res = t1.unify(t2, subm)

    if isinstance(res, UnificationError):
        if isinstance(u1, InferableQualName) and isinstance(u2, InferableQualName):
            raise InferrerError(
                f"while inferring '{u1.qualname.path}' with '{u2.qualname.path}'\n{res.message}"
            )
        if isinstance(u1, InferableQualName):
            raise InferrerError(f"while inferring '{u1.qualname.path}' with '{u2}'\n{res.message}")
        if isinstance(u2, InferableQualName):
            raise InferrerError(f"while inferring '{u2.qualname.path}' with '{u1}'\n{res.message}")
        raise InferrerError(f"while inferring types '{u1}' with '{u2}'\n{res.message}")

    if isinstance(u1, InferableQualName):
        u1.lang_type = res.lang_type
    if isinstance(u2, InferableQualName):
        u2.lang_type = res.lang_type

    return InferableUnificationResult(res.was_unified)


def try_find_inferable(path: TreePath, all_inferables: list[InferableQualName]):
    for inferable in all_inferables:
        if inferable.qualname.path == path:
            return inferable
    return None


def find_inferable(path: TreePath, all_inferables: list[InferableQualName]):
    if inferable := try_find_inferable(path, all_inferables):
        return inferable
    raise InferrerError(f"no inferrable: {path}")


def constrain_const(
    inferable: InferableQualName, subm: SubstitutionMap
) -> InferableUnificationResult:
    assert isinstance(inferable.qualname, BaseConstQualName)

    return unify(inferable, inferable.qualname.language_type, subm)


def constrain_defun(
    inferable: InferableQualName,
    defun: SExprDefun[TokenView[QualifiedToken]],
    all_inferables: list[InferableQualName],
    subm: SubstitutionMap,
) -> InferableUnificationResult:
    assert isinstance(inferable.lang_type, FunctionLanguageType)
    result = InferableUnificationResult.empty()

    for decl_arg, formal_type in zip(defun.args, inferable.lang_type.arg_types, strict=True):
        result |= unify(find_inferable(decl_arg.qualname.path, all_inferables), formal_type, subm)

    result |= unify(
        find_inferable(defun.body.qualname.path, all_inferables),
        inferable.lang_type.return_type,
        subm,
    )

    return result


def constrain_lambda(
    inferable: InferableQualName,
    lamb: SExprLambda[TokenView[QualifiedToken]],
    all_inferables: list[InferableQualName],
    subm: SubstitutionMap,
) -> InferableUnificationResult:
    assert isinstance(inferable.lang_type, FunctionLanguageType)
    result = InferableUnificationResult.empty()

    for decl_arg, formal_type in zip(lamb.args, inferable.lang_type.arg_types, strict=True):
        result |= unify(find_inferable(decl_arg.qualname.path, all_inferables), formal_type, subm)

    result |= unify(
        find_inferable(lamb.body.qualname.path, all_inferables),
        inferable.lang_type.return_type,
        subm,
    )

    return result


def constrain_generic_builtin(
    _inferable: InferableQualName, _qn: GenericBuiltinQualName
) -> InferableUnificationResult:
    return InferableUnificationResult.empty()


def constrain_projection(
    inferable: InferableQualName,
    inferable_target: InferableQualName,
    subm: SubstitutionMap,
) -> InferableUnificationResult:
    return unify(inferable, inferable_target, subm)


def constrain_usage(
    inferable: InferableQualName,
    inferable_definition: InferableQualName,
    subm: SubstitutionMap,
) -> InferableUnificationResult:
    return unify(inferable, inferable_definition, subm)


def constrain_call(
    inferable: InferableQualName,
    call: SExprCall[TokenView[QualifiedToken]],
    all_inferables: list[InferableQualName],
    make_typevar: LanguageTypeVarEmitter,
    subm: SubstitutionMap,
) -> InferableUnificationResult:
    callee_inferable = find_inferable(call.callee.qualname.path, all_inferables)
    result = InferableUnificationResult.empty()

    if isinstance(callee_inferable.lang_type, LanguageTypeVar):
        func_type = FunctionLanguageType([make_typevar() for _ in call.args], make_typevar())
        result |= unify(callee_inferable, func_type, subm)

    assert isinstance(callee_inferable.lang_type, FunctionLanguageType)

    func_type = callee_inferable.lang_type
    if len(call.args) != len(func_type.arg_types):
        raise InferrerError(
            f"Arity mismatch for '{call.callee.qualname.path}': expected {len(func_type.arg_types)}, got {len(call.args)}"
        )
    for arg_token, param_type in zip(call.args, func_type.arg_types, strict=True):
        arg_inferable = find_inferable(arg_token.qualname.path, all_inferables)
        result |= unify(arg_inferable, param_type, subm)

    result |= unify(inferable, func_type.return_type, subm)

    return result


def constrain_setq(
    inferable: InferableQualName,
    setq: SExprSetq[TokenView[QualifiedToken]],
    all_inferables: list[InferableQualName],
    subm: SubstitutionMap,
) -> InferableUnificationResult:
    target_inferable = find_inferable(setq.target.qualname.path, all_inferables)
    value_inferable = find_inferable(setq.value.qualname.path, all_inferables)
    result = unify(target_inferable, value_inferable, subm)
    result |= unify(inferable, PrimitiveLanguageType.VOID, subm)
    return result


def constrain_while(
    inferable: InferableQualName,
    while_expr: SExprWhile[TokenView[QualifiedToken]],
    all_inferables: list[InferableQualName],
    subm: SubstitutionMap,
) -> InferableUnificationResult:
    cond_inferable = find_inferable(while_expr.cond.qualname.path, all_inferables)
    result = unify(cond_inferable, PrimitiveLanguageType.BOOLEAN, subm)
    result |= unify(inferable, PrimitiveLanguageType.VOID, subm)
    return result


def constrain_if(
    inferable: InferableQualName,
    if_expr: SExprIf[TokenView[QualifiedToken]],
    all_inferables: list[InferableQualName],
    subm: SubstitutionMap,
) -> InferableUnificationResult:
    if_cond = find_inferable(if_expr.cond.qualname.path, all_inferables)
    branch_t = find_inferable(if_expr.branch_t.qualname.path, all_inferables)
    branch_f = find_inferable(if_expr.branch_f.qualname.path, all_inferables)
    result = unify(if_cond, PrimitiveLanguageType.BOOLEAN, subm)
    result |= unify(inferable, branch_t, subm)
    result |= unify(inferable, branch_f, subm)
    return result


def constrain_progn(
    inferable: InferableQualName,
    progn: "SExprProgn[TokenView[QualifiedToken]]",
    all_inferables: list[InferableQualName],
    subm: SubstitutionMap,
) -> InferableUnificationResult:
    """Тип progn -- тип последнего выражения тела (или VOID для пустого тела)."""
    if not progn.body:
        return unify(inferable, PrimitiveLanguageType.VOID, subm)
    last = find_inferable(progn.body[-1].qualname.path, all_inferables)
    return unify(inferable, last, subm)


def constrain(
    inferable: InferableQualName,
    all_inferables: list[InferableQualName],
    all_tokens: dict[TreePath, FinalToken],
    make_typevar: LanguageTypeVarEmitter,
    subm: SubstitutionMap,
) -> InferableUnificationResult:
    if isinstance(inferable.qualname, (BuiltinQualName, GenericBuiltinQualName)):
        return InferableUnificationResult.empty()

    if isinstance(inferable.qualname, BaseConstQualName):
        return constrain_const(inferable, subm)

    if isinstance(inferable.qualname, ProjectionQualName):
        target = find_inferable(inferable.qualname.definition_path, all_inferables)
        return constrain_projection(inferable, target, subm)

    if isinstance(inferable.qualname, UsageQualName):
        definition = find_inferable(inferable.qualname.definition_path, all_inferables)
        return constrain_usage(inferable, definition, subm)

    if isinstance(inferable.qualname, DefinitionQualName):
        token = all_tokens[inferable.qualname.path]
        assert isinstance(token, TokenView)

        if token.is_ident:
            return InferableUnificationResult.empty()

        s_expr = token.s_expr
        if s_expr:
            match s_expr:
                case SExprFile():
                    return unify(inferable, PrimitiveLanguageType.VOID, subm)
                case SExprProgn():
                    return constrain_progn(inferable, s_expr, all_inferables, subm)
                case SExprDefun():
                    return constrain_defun(inferable, s_expr, all_inferables, subm)
                case SExprLambda():
                    return constrain_lambda(inferable, s_expr, all_inferables, subm)
                case SExprIf():
                    return constrain_if(inferable, s_expr, all_inferables, subm)
                case SExprCall():
                    return constrain_call(inferable, s_expr, all_inferables, make_typevar, subm)
                case SExprSetq():
                    return constrain_setq(inferable, s_expr, all_inferables, subm)
                case SExprWhile():
                    return constrain_while(inferable, s_expr, all_inferables, subm)
                case never:
                    assert_never(never)

        raise InferrerError(f"Unexpected token in constraint: {token.type}")

    assert_never(inferable.qualname)


def update_all_qualnames_to_builtin_override(
    old_qualname: QualName,
    override: BuiltinQualName,
    all_tokens: dict[TreePath, FinalToken],
    all_inferables: list[InferableQualName],
):
    old_token = all_tokens[old_qualname.path]
    del all_tokens[old_qualname.path]
    assert not isinstance(old_token, VirtualToken)
    old_token.qualname = override
    all_tokens[override.path] = old_token

    for inferable in all_inferables:
        if inferable.qualname.path == old_qualname.path:
            inferable.qualname = override


@dataclass(slots=True)
class InferrerResult:
    all_inferred: list[InferredQualName]
    storage: TokenStorage[QualifiedToken]
    mutable_paths: set[TreePath]
    autoboxed_paths: set[TreePath]

    @property
    def file_token(self) -> TokenView[QualifiedToken]:
        return self.storage.file_token


def infer(res: ParserResult, use_semantic_types: bool = True) -> InferrerResult:
    initial_typevars: dict[TreePath, InferableQualName] = {}
    generic_builtin_symbols: dict[TreePath, GenericBuiltinSymbol] = {}

    def typevar_generator():
        yield from map(LanguageTypeVar, string.ascii_uppercase.replace("O", ""))

        for i in count(0):
            yield LanguageTypeVar(f"T_{i}")

    typevar_sequence = typevar_generator()

    def typevar_emitter():
        return next(typevar_sequence)

    for path, token in res.all_tokens.items():
        lang_type: InferableLanguageType

        if isinstance(token, VirtualToken) or isinstance(token.qualname, UsageQualName):
            lang_type = typevar_emitter()
        elif isinstance(token.qualname, DefinitionQualName):
            s_expr = token.s_expr
            if not s_expr:
                lang_type = typevar_emitter()
            else:
                match s_expr:
                    case SExprDefun(args=args) | SExprLambda(args):
                        lang_type = FunctionLanguageType(
                            [typevar_emitter() for _ in range(len(args))],
                            typevar_emitter(),
                        )
                    case SExprCall():
                        lang_type = typevar_emitter()
                    case _:
                        lang_type = typevar_emitter()

        elif isinstance(token.qualname, ProjectionQualName):
            lang_type = typevar_emitter()

        elif isinstance(token.qualname, BuiltinQualName):
            if use_semantic_types:
                lang_type = token.qualname.symbol.semantic_lang_type_builder(typevar_emitter)
            else:
                lang_type = token.qualname.symbol.lang_type_builder(typevar_emitter)

        elif isinstance(token.qualname, GenericBuiltinQualName):
            generic_builtin_symbols[path] = token.qualname.symbol_builder(
                typevar_emitter, use_semantic_types
            )
            lang_type = typevar_emitter()

        elif isinstance(token.qualname, BaseConstQualName):
            lang_type = token.qualname.language_type

        else:
            assert_never(token.qualname)

        if path in initial_typevars:
            raise InferrerError(f"path override: {path}")
        initial_typevars[path] = InferableQualName(token.qualname, token, lang_type)

    all_inferables = list(initial_typevars.values())
    subm: SubstitutionMap = {}

    changed = True
    while changed:
        changed = False

        infer_changed = True
        while infer_changed:
            infer_changed = False
            for inferred in all_inferables:
                result = constrain(inferred, all_inferables, res.all_tokens, typevar_emitter, subm)
                infer_changed |= result.was_unified
                changed |= infer_changed

        mono_changed = True
        while mono_changed:
            mono_changed = False

            for inferred in all_inferables:
                if isinstance(inferred.qualname, GenericBuiltinQualName):
                    generic_builtin_symbol = generic_builtin_symbols[inferred.qualname.path]
                    if overload := generic_builtin_symbol.resolve_override(
                        inferred.lang_type, subm, is_soft=True
                    ):
                        unify(inferred.lang_type, overload.lang_type, subm)
                        update_all_qualnames_to_builtin_override(
                            inferred.qualname,
                            BuiltinQualName(overload.symbol),
                            res.all_tokens,
                            all_inferables,
                        )
                        mono_changed |= True
                        changed |= mono_changed

    inferred_qualnames: list[InferredQualName] = []

    failed: list[InferableQualName] = []

    for inferred in all_inferables:
        resolved_type = inferred.lang_type.deref(subm)

        if not resolved_type.is_complete(subm):
            failed.append(inferred)
            continue
        completed = resolved_type.complete(subm)
        assert completed is not None

        if isinstance(
            inferred.qualname,
            (
                DefinitionQualName,
                UsageQualName,
                ProjectionQualName,
                BuiltinQualName,
                BaseConstQualName,
            ),
        ):
            inferred_qualnames.append(
                InferredQualName(
                    qualname=inferred.qualname,
                    token=inferred.token,
                    lang_type=completed,
                )
            )
        elif isinstance(inferred.qualname, GenericBuiltinQualName):
            try:
                generic_builtin_symbol = generic_builtin_symbols[inferred.qualname.path]
                overload = generic_builtin_symbol.resolve_override(
                    inferred.lang_type, subm, is_soft=False
                )

                unify(inferred.lang_type, overload.lang_type, subm)
                builtin_qualname = BuiltinQualName(overload.symbol)
                resolved_type2 = completed.deref(subm)

                if not resolved_type2.is_complete(subm):
                    raise InferrerError(
                        f"Не удалось вывести все типы: {inferred.qualname.path} = {resolved_type2}"
                    )
                completed2 = resolved_type2.complete(subm)
                assert completed2 is not None

                update_all_qualnames_to_builtin_override(
                    inferred.qualname, builtin_qualname, res.all_tokens, all_inferables
                )
            except InferrerError as e:
                raise InferrerError(
                    f"Ошибка вывода типа generic '{inferred.qualname.path}' [{inferred.lang_type}]"
                ) from e
            inferred_qualnames.append(
                InferredQualName(
                    qualname=builtin_qualname,
                    token=inferred.token,
                    lang_type=completed2,
                )
            )
        else:
            assert_never(inferred.qualname)

    if len(failed) > 0:
        raise InferrerError(
            f"Unable to determine all types:\n{
                ('\n'.join(f'{f.qualname.path} = {f.lang_type.deref(subm)}' for f in failed))
            }"
        )

    return InferrerResult(inferred_qualnames, res.storage, res.mutable_paths, res.autoboxed_paths)
