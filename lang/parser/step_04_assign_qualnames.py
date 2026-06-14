from dataclasses import dataclass
from typing import Callable, Protocol, TypeVar, assert_never, cast

from lang.parser.builtin_symbols import GenericBuiltinSymbolBuilder

from .find_builtin_symbol import find_builtin_symbol, find_generic_builtin_symbol_builder
from .step_02_analyze_s_expr import SExprCall, SExprDefun, SExprFile, SExprIf, SExprLambda, SExprProgn, Token_Step_02
from .qualname import BooleanConstQualName, BuiltinQualName, BuiltinSymbol, DefinitionQualName, FloatConstQualName, GenericBuiltinQualName, IntegerConstQualName, ProjectionQualName, QualName, StringConstQualName, TreePath, TreePathEntry, UsageQualName


@dataclass
class Token_Step_04(Token_Step_02):
    qualname: QualName


@dataclass
class VirtualToken:
    qualname: ProjectionQualName


type FinalToken = Token_Step_04 | VirtualToken


def assign_qualname(token: Token_Step_02, qualname: QualName) -> Token_Step_04:
    return token.extend(Token_Step_04, qualname=qualname)


TreeTraverserStateT = TypeVar("TreeTraverserStateT")


class TreeTraverser(Protocol):
    def __call__(
        self,
        token: Token_Step_02,
        state: TreeTraverserStateT,
        fn: Callable[[Token_Step_02, TreePath, TreeTraverserStateT], TreeTraverserStateT],
        path: TreePath = TreePathEntry.for_file().as_entire_tree_path()
    ):
        ...


def tree_traverser(
    token: Token_Step_02,
    state: TreeTraverserStateT,
    fn: Callable[[Token_Step_02, TreePath, TreeTraverserStateT], TreeTraverserStateT],
    path: TreePath = TreePathEntry.for_file().as_entire_tree_path()
):
    if token.s_expr:
        match token.s_expr:
            case SExprFile(body):
                cur_path = TreePathEntry.for_file().as_entire_tree_path()
                state = fn(token, cur_path, state)
                for i, st in enumerate(body):
                    st_path = cur_path.combine(TreePathEntry.for_statement(i))
                    tree_traverser(st, state, fn, st_path)
            case SExprDefun(symbol, args, body):
                cur_path = TreePathEntry.for_scope(symbol).as_entire_tree_path()
                state = fn(token, cur_path, state)
                for arg in args:
                    tree_traverser(arg, state, fn, cur_path)
                tree_traverser(body, state, fn, cur_path.combine(TreePathEntry.for_body()))
            case SExprLambda(args, body):
                cur_path = path.combine(TreePathEntry.for_scope("lambda"))
                state = fn(token, cur_path, state)
                for arg in args:
                    tree_traverser(arg, state, fn, cur_path)
                tree_traverser(body, state, fn, cur_path.combine(TreePathEntry.for_body()))
            case SExprCall(callee, args):
                if callee.is_ident:
                    entry = TreePathEntry.for_named_call(callee.source)
                else:
                    entry = TreePathEntry.for_anon_call()
                cur_path = path.combine(entry)
                state = fn(token, cur_path, state)
                tree_traverser(callee, state, fn, cur_path)
                for i, arg in enumerate(args):
                    arg_path = cur_path.combine(TreePathEntry.for_call_arg(i))
                    tree_traverser(arg, state, fn, arg_path)
            case SExprIf(cond, branch_t, branch_f):
                cur_path = path.combine(TreePathEntry.for_if())
                state = fn(token, cur_path, state)
                tree_traverser(cond, state, fn, cur_path.combine(TreePathEntry.for_cond()))
                tree_traverser(branch_t, state, fn, cur_path.combine(TreePathEntry.for_branch_t()))
                tree_traverser(branch_f, state, fn, cur_path.combine(TreePathEntry.for_branch_f()))
            case SExprProgn(body):
                cur_path = path.combine(TreePathEntry.for_progn())
                state = fn(token, cur_path, state)
                for i, st in enumerate(body):
                    st_path = cur_path.combine(TreePathEntry.for_statement(i))
                    tree_traverser(st, state, fn, st_path)
            case never:
                assert_never(never)
    elif token.is_ident:
        cur_path = path.combine(TreePathEntry.for_ident(token.source))
        fn(token, cur_path, state)
    elif token.is_integer or token.is_float or token.is_boolean or token.is_string:
        cur_path = TreePathEntry.for_const(token.source).as_entire_tree_path()
        fn(token, cur_path, state)
    else:
        raise NotImplementedError()


@dataclass
class ScopeBinding:
    definition_path: TreePath
    scope_path: TreePath


def step_04_assign_qualnames(file_token: Token_Step_02) -> Step_04_AssignQualnamesResult:
    all_real_tokens: dict[TreePath, Token_Step_04] = {}
    new_file_token: Token_Step_04 | None = cast(Token_Step_04 | None, None)
    global_defun_paths: dict[str, TreePath] = {}
    virtual_tokens: dict[TreePath, VirtualToken] = {}
    all_tokens: dict[TreePath, FinalToken]

    def collect_defuns(token: Token_Step_02, path: TreePath, *_ignore):
        if token.s_expr and isinstance(token.s_expr, SExprDefun):
            sym = token.s_expr.symbol
            if sym in global_defun_paths:
                raise NameError(f"Duplicate global defun '{sym}'")
            global_defun_paths[sym] = path

    def assign_qualnames(
        token: Token_Step_02,
        path: TreePath,
        env: dict[str, ScopeBinding]
    ):
        nonlocal new_file_token

        if token.s_expr:
            qn = DefinitionQualName(path)
        elif token.is_ident:
            if binding := env.get(token.source):
                if binding.definition_path == path:
                    qn = DefinitionQualName(path)
                else:
                    qn = UsageQualName(
                        TreePathEntry.for_usage(path, binding.definition_path).as_entire_tree_path(),
                        binding.definition_path
                    )
            elif defun_path := global_defun_paths.get(token.source):
                qn = UsageQualName(
                    TreePathEntry.for_usage(path, defun_path).as_entire_tree_path(),
                    defun_path
                )
            elif symbol := find_builtin_symbol(token.source):
                qn = BuiltinQualName(symbol)
            elif builder := find_generic_builtin_symbol_builder(token.source):
                qn = GenericBuiltinQualName(path, builder)
            else:
                raise NameError(f"Unbound variable '{token.source}' at '{path}'")
        else:
            if token.is_integer:
                qn = IntegerConstQualName(path, token.source, int(token.source))
            elif token.is_float:
                qn = FloatConstQualName(path, token.source, float(token.source))
            elif token.is_boolean:
                qn = BooleanConstQualName(path, token.source, token.source == "true")
            elif token.is_string:
                qn = StringConstQualName(path, token.source, token.source)
            else:
                raise NotImplementedError(f"Unknown const token: {type(token)}")

        new_token = assign_qualname(token, qn)
        all_real_tokens[qn.path] = new_token

        if isinstance(token.s_expr, SExprFile):
            new_file_token = new_token

        new_env: dict[str, ScopeBinding] = env.copy()
        if token.s_expr and isinstance(token.s_expr, SExprDefun):
            new_env = {}
        elif token.s_expr and isinstance(token.s_expr, SExprLambda):
            for k, v in env.items():
                projection_path = TreePathEntry.for_projection(v.definition_path, path).as_entire_tree_path()
                new_env[k] = ScopeBinding(projection_path, path)
                virtual_tokens[projection_path] = VirtualToken(ProjectionQualName(
                    projection_path, v.definition_path, path
                ))

        if token.s_expr and isinstance(token.s_expr, (SExprDefun, SExprLambda)):
            for arg in token.s_expr.args:
                arg_path = path.combine(TreePathEntry.for_ident(arg.source))
                new_env[arg.source] = ScopeBinding(arg_path, path)

        return new_env

    tree_traverser(token=file_token, state=None, fn=collect_defuns)
    tree_traverser(token=file_token, state={}, fn=assign_qualnames)

    used_virtual_tokens = {
        path: vtoken
        for path, vtoken in virtual_tokens.items()
        if any(
            path == token.qualname.definition_path
            for token in all_real_tokens.values()
            if isinstance(token.qualname, UsageQualName)
        )
    }

    for _ in range(len(virtual_tokens)):
        for path, current_vtoken in virtual_tokens.items():
            if any(
                path == vtoken.qualname.definition_path
                for vtoken in used_virtual_tokens.values()
            ):
                used_virtual_tokens[path] = current_vtoken

    all_tokens = {
        **all_real_tokens,
        **{
            path: vtoken
            for path, vtoken in virtual_tokens.items()
            if path in used_virtual_tokens
        }
    }

    assert new_file_token
    return Step_04_AssignQualnamesResult(new_file_token, all_tokens)


@dataclass
class Step_04_AssignQualnamesResult:
    file_token: Token_Step_04
    all_tokens: dict[TreePath, FinalToken]
