from dataclasses import dataclass
from itertools import count
import string
from typing import Self, assert_never, cast

from lang.lang_type import FunctionLanguageType, InferableLanguageType, LanguageType, LanguageTypeVar, PrimitiveLanguageType, SubstitutionMap, UnificationError
from lang.parser import ParserResult
from lang.parser.qualname import BaseConstQualName, BuiltinQualName, ConstQualName, DefinitionQualName, GenericBuiltinQualName, GenericBuiltinSymbol, LanguageTypeVarEmitter, ProjectionQualName, QualName, TreePath, UsageQualName
from lang.parser.step_02_analyze_s_expr import SExprCall, SExprDefun, SExprFile, SExprIf, SExprLambda, SExprProgn
from lang.parser.step_04_assign_qualnames import FinalToken, Token_Step_04, VirtualToken


@dataclass
class InferableQualName:
    qualname: QualName
    token: FinalToken
    lang_type: LanguageType | InferableLanguageType


@dataclass
class InferredQualName:
    qualname: BuiltinQualName | UsageQualName | DefinitionQualName | ProjectionQualName | ConstQualName
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
    subm: SubstitutionMap
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
            raise Exception(f"while inferring '{u1.qualname.path}' with '{u2.qualname.path}'\n{res.message}")
        if isinstance(u1, InferableQualName):
            raise Exception(f"while inferring '{u1.qualname.path}' with '{u2}'\n{res.message}")
        if isinstance(u2, InferableQualName):
            raise Exception(f"while inferring '{u2.qualname.path}' with '{u1}'\n{res.message}")
        raise Exception(f"while inferring types '{u1}' with '{u2}'\n{res.message}")

    if isinstance(u1, InferableQualName):
        u1.lang_type = res.lang_type
    if isinstance(u2, InferableQualName):
        u2.lang_type = res.lang_type

    #if isinstance(u1, InferableQualName) and isinstance(u2, InferableQualName):
    #    print(f"unify '{u1.qualname.path}' [{t1}] with '{u2.qualname.path} [{t2}]' -> {res.lang_type} [{res.was_unified}]")
    #elif isinstance(u1, InferableQualName):
    #    print(f"unify '{u1.qualname.path}' [{t1}] with '{u2}' -> {res.lang_type} [{res.was_unified}]")
    #elif isinstance(u2, InferableQualName):
    #    print(f"unify '{u2.qualname.path}' [{t2}] with '{u1}' -> {res.lang_type} [{res.was_unified}]")

    return InferableUnificationResult(res.was_unified)


def try_find_inferable(path: TreePath, all_inferables: list[InferableQualName]):
    for inferable in all_inferables:
        if inferable.qualname.path == path:
            return inferable
    return None


def find_inferable(path: TreePath, all_inferables: list[InferableQualName]):
    if inferable := try_find_inferable(path, all_inferables):
        return inferable
    raise Exception(f"no inferrable: {path}")


def constrain_const(
    inferable: InferableQualName,
    subm: SubstitutionMap
) -> InferableUnificationResult:
    assert isinstance(inferable.qualname, BaseConstQualName)

    return unify(inferable, inferable.qualname.language_type, subm)


def constrain_defun(
    inferable: InferableQualName,
    defun: SExprDefun[Token_Step_04],
    all_inferables: list[InferableQualName],
    subm: SubstitutionMap
) -> InferableUnificationResult:
    assert isinstance(inferable.lang_type, FunctionLanguageType)
    result = InferableUnificationResult.empty()

    for decl_arg, formal_type in zip(defun.args, inferable.lang_type.arg_types):
        result |= unify(
            find_inferable(decl_arg.qualname.path, all_inferables),
            formal_type,
            subm
        )

    result |= unify(
        find_inferable(defun.body.qualname.path, all_inferables),
        inferable.lang_type.return_type,
        subm
    )

    return result


def constrain_lambda(
    inferable: InferableQualName,
    lamb: SExprLambda[Token_Step_04],
    all_inferables: list[InferableQualName],
    subm: SubstitutionMap
) -> InferableUnificationResult:
    assert isinstance(inferable.lang_type, FunctionLanguageType)
    result = InferableUnificationResult.empty()

    for decl_arg, formal_type in zip(lamb.args, inferable.lang_type.arg_types):
        result |= unify(
            find_inferable(decl_arg.qualname.path, all_inferables),
            formal_type,
            subm
        )

    result |= unify(
        find_inferable(lamb.body.qualname.path, all_inferables),
        inferable.lang_type.return_type,
        subm
    )

    return result


def constrain_generic_builtin(
    _inferable: InferableQualName,
    _qn: GenericBuiltinQualName
) -> InferableUnificationResult:
    return InferableUnificationResult.empty()


def constrain_projection(
    inferable: InferableQualName,
    inferable_target: InferableQualName,
    subm: SubstitutionMap
) -> InferableUnificationResult:
    return unify(inferable, inferable_target, subm)


def constrain_usage(
    inferable: InferableQualName,
    inferable_definition: InferableQualName,
    subm: SubstitutionMap
) -> InferableUnificationResult:
    return unify(inferable, inferable_definition, subm)


def constrain_call(
    inferable: InferableQualName,
    call: SExprCall[Token_Step_04],
    all_inferables: list[InferableQualName],
    make_typevar: LanguageTypeVarEmitter,
    subm: SubstitutionMap
) -> InferableUnificationResult:
    callee_inferable = find_inferable(call.callee.qualname.path, all_inferables)
    result = InferableUnificationResult.empty()

    if isinstance(callee_inferable.lang_type, LanguageTypeVar):
        func_type = FunctionLanguageType(
            [make_typevar() for _ in call.args],
            make_typevar()
        )
        result |= unify(callee_inferable, func_type, subm)

    assert isinstance(callee_inferable.lang_type, FunctionLanguageType)

    func_type = callee_inferable.lang_type
    if len(call.args) != len(func_type.arg_types):
        raise Exception(f"Arity mismatch for '{call.callee.qualname.path}': expected {len(func_type.arg_types)}, got {len(call.args)}")
    for arg_token, param_type in zip(call.args, func_type.arg_types):
        arg_inferable = find_inferable(arg_token.qualname.path, all_inferables)
        result |= unify(arg_inferable, param_type, subm)

    result |= unify(inferable, func_type.return_type, subm)

    return result


def constrain_if(
    inferable: InferableQualName,
    if_expr: SExprIf[Token_Step_04],
    all_inferables: list[InferableQualName],
    subm: SubstitutionMap
) -> InferableUnificationResult:
    if_cond = find_inferable(if_expr.cond.qualname.path, all_inferables)
    branch_t = find_inferable(if_expr.branch_t.qualname.path, all_inferables)
    branch_f = find_inferable(if_expr.branch_f.qualname.path, all_inferables)
    result = unify(if_cond, PrimitiveLanguageType.BOOLEAN, subm)
    result |= unify(inferable, branch_t, subm)
    result |= unify(inferable, branch_f, subm)
    return result


def constrain(
    inferable: InferableQualName,
    all_inferables: list[InferableQualName],
    all_tokens: dict[TreePath, FinalToken],
    make_typevar: LanguageTypeVarEmitter,
    subm: SubstitutionMap
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
        assert isinstance(token, Token_Step_04)

        if token.is_ident:
            return InferableUnificationResult.empty()

        if token.s_expr:
            match token.s_expr:
                case SExprFile() | SExprProgn():
                    return unify(inferable, PrimitiveLanguageType.VOID, subm)
                case SExprDefun():
                    return constrain_defun(inferable, token.s_expr, all_inferables, subm)
                case SExprLambda():
                    return constrain_lambda(inferable, token.s_expr, all_inferables, subm)
                case SExprIf():
                    return constrain_if(inferable, token.s_expr, all_inferables, subm)
                case SExprCall():
                    return constrain_call(inferable, token.s_expr, all_inferables, make_typevar, subm)
                case never:
                    assert_never(never)

        raise NotImplementedError()

    assert_never(inferable.qualname)


def update_all_qualnames_to_builtin_override(
    old_qualname: QualName,
    override: BuiltinQualName,
    all_tokens: dict[TreePath, FinalToken],
    all_inferables: list[InferableQualName]
):
    old_token = all_tokens[old_qualname.path]
    del all_tokens[old_qualname.path]
    assert not isinstance(old_token, VirtualToken)
    old_token.qualname = override
    all_tokens[override.path] = old_token

    for inferable in all_inferables:
        if inferable.qualname.path == old_qualname.path:
            inferable.qualname = override


def infer(
    res: ParserResult
) -> InferrerResult:
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

        if isinstance(token, VirtualToken):
            lang_type = typevar_emitter()
        elif isinstance(token.qualname, UsageQualName):
            lang_type = typevar_emitter()
        elif isinstance(token.qualname, DefinitionQualName):
            if not token.s_expr:
                lang_type = typevar_emitter()
            else:
                match token.s_expr:
                    case SExprDefun(args=args) | SExprLambda(args):
                        lang_type = FunctionLanguageType(
                            [typevar_emitter() for _ in range(len(args))],
                            typevar_emitter()
                        )
                    case SExprCall():
                        lang_type = typevar_emitter()
                    case _:
                        lang_type = typevar_emitter()

        elif isinstance(token.qualname, ProjectionQualName):
            lang_type = typevar_emitter()

        elif isinstance(token.qualname, BuiltinQualName):
            lang_type = token.qualname.symbol.lang_type_builder(typevar_emitter)

        elif isinstance(token.qualname, GenericBuiltinQualName):
            generic_builtin_symbols[path] = token.qualname.symbol_builder(typevar_emitter)
            lang_type = typevar_emitter()

        elif isinstance(token.qualname, BaseConstQualName):
            lang_type = token.qualname.language_type

        else:
            assert_never(token.qualname)

        if path in initial_typevars:
            raise Exception(f"path override: {path}")
        initial_typevars[path] = InferableQualName(token.qualname, token, lang_type)

    #for path, inferable in initial_typevars.items():
    #    print("Initially", path, " = ", inferable.lang_type)

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
                    if overload := generic_builtin_symbol.resolve_override(inferred.lang_type, subm, is_soft=True):
                        unify(inferred.lang_type, overload.lang_type, subm)
                        update_all_qualnames_to_builtin_override(
                            inferred.qualname,
                            BuiltinQualName(overload.symbol),
                            res.all_tokens,
                            all_inferables
                        )
                        mono_changed |= True
                        changed |= mono_changed

    inferred_qualnames: list[InferredQualName] = []

    for inferred in all_inferables:
        resolved_type = inferred.lang_type.deref(subm)

        if not resolved_type.is_complete(subm):
            raise Exception(f"Unable to determine all types: {inferred.qualname.path} = {resolved_type}")
        resolved_type = resolved_type.complete(subm)
        assert resolved_type

        if isinstance(inferred.qualname, (
            DefinitionQualName,
            UsageQualName,
            ProjectionQualName,
            BuiltinQualName,
            BaseConstQualName
        )):
            inferred_qualnames.append(InferredQualName(
                qualname=inferred.qualname,
                token=inferred.token,
                lang_type=resolved_type
            ))
        elif isinstance(inferred.qualname, GenericBuiltinQualName):
            try:
                generic_builtin_symbol = generic_builtin_symbols[inferred.qualname.path]
                overload = generic_builtin_symbol.resolve_override(inferred.lang_type, subm, is_soft=False)

                unify(inferred.lang_type, overload.lang_type, subm)
                builtin_qualname = BuiltinQualName(overload.symbol)
                resolved_type = resolved_type.deref(subm)

                if not resolved_type.is_complete(subm):
                    raise Exception(f"Unable to determine all types: {inferred.qualname.path} = {resolved_type}")
                resolved_type = resolved_type.complete(subm)
                assert resolved_type

                update_all_qualnames_to_builtin_override(
                    inferred.qualname,
                    builtin_qualname,
                    res.all_tokens,
                    all_inferables
                )
            except Exception as e:
                raise Exception(f"Infer fail with generic '{inferred.qualname.path}' [{inferred.lang_type}]") from e
            inferred_qualnames.append(InferredQualName(
                qualname=builtin_qualname,
                token=inferred.token,
                lang_type=resolved_type
            ))
        else:
            assert_never(inferred.qualname)

    return InferrerResult(
        inferred_qualnames,
        res.file_token
    )


@dataclass(slots=True)
class InferrerResult:
    all_inferred: list[InferredQualName]
    file_token: Token_Step_04
