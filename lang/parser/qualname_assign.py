from __future__ import annotations

import struct
from collections.abc import Callable
from ctypes import c_double, c_float, c_int32, c_uint32
from dataclasses import dataclass
from typing import assert_never

from lang.exceptions import ParserError
from lang.stdlib import (
    find_builtin_symbol,
    find_generic_builtin_symbol_builder,
)

from .qualname import (
    BooleanConstQualName,
    BuiltinQualName,
    DefinitionQualName,
    DoubleConstQualName,
    FloatConstQualName,
    GenericBuiltinQualName,
    IntegerConstQualName,
    ProjectionQualName,
    QualName,
    StringConstQualName,
    TreePath,
    TreePathEntry,
    UsageQualName,
)
from .s_expr import (
    SemanticToken,
    SExprCall,
    SExprDefun,
    SExprFile,
    SExprIf,
    SExprLambda,
    SExprProgn,
    SExprSetq,
    SExprWhile,
)
from .token_storage import TokenStorage, TokenView


@dataclass
class QualifiedToken(SemanticToken):
    qualname: QualName

    @classmethod
    def from_semantic(cls, token: SemanticToken, qualname: QualName) -> QualifiedToken:
        return cls(
            _source=token._source,
            type=token.type,
            _children=token._children,
            _s_expr=token._s_expr,
            qualname=qualname,
        )


@dataclass
class VirtualToken:
    qualname: ProjectionQualName


type FinalToken = TokenView[QualifiedToken] | VirtualToken


def tree_traverser[TreeTraverserStateT](
    view: TokenView[SemanticToken],
    state: TreeTraverserStateT,
    fn: Callable[[TokenView[SemanticToken], TreePath, TreeTraverserStateT], TreeTraverserStateT],
    path: TreePath | None = None,
):
    path = path or TreePathEntry.for_file().as_entire_tree_path()
    s_expr = view.s_expr
    if s_expr:
        match s_expr:
            case SExprFile(body):
                cur_path = TreePathEntry.for_file().as_entire_tree_path()
                state = fn(view, cur_path, state)
                for i, st_view in enumerate(body):
                    st_path = cur_path.combine(TreePathEntry.for_statement(i))
                    tree_traverser(st_view, state, fn, st_path)
            case SExprDefun(symbol, args, body):
                cur_path = TreePathEntry.for_scope(symbol).as_entire_tree_path()
                state = fn(view, cur_path, state)
                for arg_view in args:
                    tree_traverser(arg_view, state, fn, cur_path)
                tree_traverser(body, state, fn, cur_path.combine(TreePathEntry.for_body()))
            case SExprLambda(args, body):
                cur_path = path.combine(TreePathEntry.for_scope("lambda"))
                state = fn(view, cur_path, state)
                for arg_view in args:
                    tree_traverser(arg_view, state, fn, cur_path)
                tree_traverser(body, state, fn, cur_path.combine(TreePathEntry.for_body()))
            case SExprCall(callee, args):
                if callee.is_ident:
                    entry = TreePathEntry.for_named_call(callee.source)
                else:
                    entry = TreePathEntry.for_anon_call()
                cur_path = path.combine(entry)
                state = fn(view, cur_path, state)
                tree_traverser(callee, state, fn, cur_path)
                for i, arg_view in enumerate(args):
                    arg_path = cur_path.combine(TreePathEntry.for_call_arg(i))
                    tree_traverser(arg_view, state, fn, arg_path)
            case SExprIf(cond, branch_t, branch_f):
                cur_path = path.combine(TreePathEntry.for_if())
                state = fn(view, cur_path, state)
                tree_traverser(cond, state, fn, cur_path.combine(TreePathEntry.for_cond()))
                tree_traverser(branch_t, state, fn, cur_path.combine(TreePathEntry.for_branch_t()))
                tree_traverser(branch_f, state, fn, cur_path.combine(TreePathEntry.for_branch_f()))
            case SExprProgn(body):
                cur_path = path.combine(TreePathEntry.for_progn())
                state = fn(view, cur_path, state)
                for i, st_view in enumerate(body):
                    st_path = cur_path.combine(TreePathEntry.for_statement(i))
                    tree_traverser(st_view, state, fn, st_path)
            case SExprSetq(target, value):
                cur_path = path.combine(TreePathEntry.for_named_call("setq"))
                state = fn(view, cur_path, state)
                tree_traverser(target, state, fn, cur_path)
                tree_traverser(value, state, fn, cur_path)
            case SExprWhile(cond, body):
                cur_path = path.combine(TreePathEntry.for_named_call("while"))
                state = fn(view, cur_path, state)
                tree_traverser(cond, state, fn, cur_path.combine(TreePathEntry.for_cond()))
                tree_traverser(body, state, fn, cur_path.combine(TreePathEntry.for_body()))
            case never:
                assert_never(never)
    elif view.is_ident:
        cur_path = path.combine(TreePathEntry.for_ident(view.source))
        fn(view, cur_path, state)
    elif view.is_integer or view.is_float or view.is_double or view.is_boolean or view.is_string:
        cur_path = TreePathEntry.for_const(view.source).as_entire_tree_path()
        fn(view, cur_path, state)
    else:
        raise ParserError(f"Unexpected token type in tree traversal: {view.type}")


@dataclass
class ScopeBinding:
    definition_path: TreePath
    scope_path: TreePath


@dataclass
class QualNameResult:
    storage: TokenStorage[QualifiedToken]
    all_tokens: dict[TreePath, FinalToken]
    mutable_paths: set[TreePath]
    autoboxed_paths: set[TreePath]


def assign_qualnames(
    storage: TokenStorage[SemanticToken],
) -> QualNameResult:
    qualname_map: dict[int, QualName] = {}
    global_defun_paths: dict[str, TreePath] = {}
    virtual_tokens: dict[TreePath, VirtualToken] = {}

    def collect_defuns(view: TokenView[SemanticToken], path: TreePath, *_ignore):
        s_expr = view.s_expr
        if s_expr and isinstance(s_expr, SExprDefun):
            sym = s_expr.symbol
            if sym in global_defun_paths:
                raise ParserError(f"Duplicate global defun '{sym}'")
            global_defun_paths[sym] = path

    def visit_node(view: TokenView[SemanticToken], path: TreePath, env: dict[str, ScopeBinding]):
        s_expr = view.s_expr
        qn: QualName
        if s_expr:
            qn = DefinitionQualName(path)
        elif view.is_ident:
            if binding := env.get(view.source):
                if binding.definition_path == path:
                    qn = DefinitionQualName(path)
                else:
                    qn = UsageQualName(
                        TreePathEntry.for_usage(
                            path, binding.definition_path
                        ).as_entire_tree_path(),
                        binding.definition_path,
                    )
            elif defun_path := global_defun_paths.get(view.source):
                qn = UsageQualName(
                    TreePathEntry.for_usage(path, defun_path).as_entire_tree_path(),
                    defun_path,
                )
            elif symbol := find_builtin_symbol(view.source):
                qn = BuiltinQualName(symbol)
            elif builder := find_generic_builtin_symbol_builder(view.source):
                qn = GenericBuiltinQualName(path, builder)
            else:
                raise ParserError(f"Unbound variable '{view.source}' at '{path}'")
        else:
            if view.is_integer:
                ival = c_int32(int(view.source))
                if ival.value != int(view.source):
                    raise ParserError(f"{view.source} is out of bounds of int32")
                qn = IntegerConstQualName(path, view.source, ival)
            elif view.is_float:
                fval = c_float(float(view.source))
                qn = FloatConstQualName(path, view.source, fval)
            elif view.is_double:
                dval = c_double(float(view.source.rstrip("dD")))
                qn = DoubleConstQualName(path, view.source, dval)
            elif view.is_boolean:
                qn = BooleanConstQualName(path, view.source, view.source == "true")
            elif view.is_string:
                sval = [
                    c_uint32(n)
                    for (n,) in struct.iter_unpack("<I", view.source[1:-1].encode("utf-32le"))
                ]
                qn = StringConstQualName(path, view.source, sval)
            else:
                raise ParserError(f"Unknown const token: {view.type}")

        qualname_map[view.index] = qn

        new_env: dict[str, ScopeBinding] = env.copy()
        if s_expr and isinstance(s_expr, SExprDefun):
            new_env = {}
        elif s_expr and isinstance(s_expr, SExprLambda):
            for k, v in env.items():
                projection_path = TreePathEntry.for_projection(
                    v.definition_path, path
                ).as_entire_tree_path()
                new_env[k] = ScopeBinding(projection_path, path)
                virtual_tokens[projection_path] = VirtualToken(
                    ProjectionQualName(projection_path, v.definition_path, path)
                )

        if s_expr and isinstance(s_expr, (SExprDefun, SExprLambda)):
            for arg_view in s_expr.args:
                arg_path = path.combine(TreePathEntry.for_ident(arg_view.source))
                new_env[arg_view.source] = ScopeBinding(arg_path, path)

        return new_env

    tree_traverser(view=storage.file_token, state=None, fn=collect_defuns)
    tree_traverser(view=storage.file_token, state={}, fn=visit_node)

    def promote_token(tok: SemanticToken, idx: int) -> QualifiedToken:
        if idx in qualname_map:
            return QualifiedToken.from_semantic(tok, qualname_map[idx])

        # Parser/CPS scaffolding tokens can remain in storage after traversal, but
        # they are intentionally absent from all_tokens.
        internal_path = TreePathEntry.for_ident(f"__syntax_{idx}").as_entire_tree_path()
        return QualifiedToken.from_semantic(tok, DefinitionQualName(internal_path))

    new_storage = storage.promote(promote_token)

    all_real_tokens: dict[TreePath, TokenView[QualifiedToken]] = {}
    for idx, qn in qualname_map.items():
        view = new_storage.view(idx)
        all_real_tokens[qn.path] = view

    used_virtual_tokens = {
        path: vtoken
        for path, vtoken in virtual_tokens.items()
        if any(
            path == real_view.qualname.definition_path
            for real_view in all_real_tokens.values()
            if isinstance(real_view.qualname, UsageQualName)
        )
    }

    for _ in range(len(virtual_tokens)):
        for path, current_vtoken in virtual_tokens.items():
            if any(
                path == vtoken.qualname.definition_path for vtoken in used_virtual_tokens.values()
            ):
                used_virtual_tokens[path] = current_vtoken

    all_tokens: dict[TreePath, FinalToken] = {
        **all_real_tokens,
        **{path: vtoken for path, vtoken in virtual_tokens.items() if path in used_virtual_tokens},
    }

    mutable_paths: set[TreePath] = set()
    for idx, _ in qualname_map.items():
        token = new_storage.get(idx)
        s_expr = token._s_expr
        if isinstance(s_expr, SExprSetq):
            target_qn = qualname_map.get(s_expr.target)
            if isinstance(target_qn, UsageQualName):
                mutable_paths.add(target_qn.definition_path)

    captured_paths: set[TreePath] = set()
    for vtoken in used_virtual_tokens.values():
        if isinstance(vtoken.qualname, ProjectionQualName):
            captured_paths.add(vtoken.qualname.definition_path)

    autoboxed_paths = mutable_paths & captured_paths

    projections = [
        vtoken.qualname
        for vtoken in used_virtual_tokens.values()
        if isinstance(vtoken.qualname, ProjectionQualName)
    ]
    changed = True
    while changed:
        changed = False
        for pqn in projections:
            if pqn.path not in autoboxed_paths and pqn.definition_path in autoboxed_paths:
                autoboxed_paths.add(pqn.path)
                changed = True
            if pqn.path in autoboxed_paths and pqn.definition_path not in autoboxed_paths:
                autoboxed_paths.add(pqn.definition_path)
                changed = True

    return QualNameResult(new_storage, all_tokens, mutable_paths, autoboxed_paths)
