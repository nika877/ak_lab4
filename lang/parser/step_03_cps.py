from typing import Sequence

from .find_builtin_symbol import find_builtin_symbol, find_generic_builtin_symbol_builder
from .step_01_build_tree import RECURSIVE_SOURCE, RecursiveSource, ParserTokenType, Token_Step_01
from .step_02_analyze_s_expr import Token_Step_02, SExprCall, SExprDefun, SExprFile, SExprIf, SExprLambda, SExprProgn


class CPSTransformer:
    def __init__(self) -> None:
        self._counter = 0

    def _is_s_expr_atomic(self, s_expr: SExprCall[Token_Step_02]) -> bool:
        return (
            find_builtin_symbol(s_expr.callee.source) is not None
            or
            find_generic_builtin_symbol_builder(s_expr.callee.source) is not None
        )

    def _next_id(self, prefix: str) -> str:
        val = f"{prefix}{self._counter}"
        self._counter += 1
        return val

    def _fresh_token(
        self,
        source: str | RecursiveSource,
        type: ParserTokenType,
        children: list[Token_Step_02]
    ) -> Token_Step_02:
        t = Token_Step_01(_source=source, type=type, _children=children)
        return t.extend(Token_Step_02, _s_expr=None)

    def _make_file(self, callee: Token_Step_02, body: Sequence[Token_Step_02]) -> Token_Step_02:
        tok = self._fresh_token(RECURSIVE_SOURCE, ParserTokenType.S_EXPR, [callee] + list(body))
        tok._s_expr = SExprFile(body=body)
        return tok

    def _make_call(self, callee: Token_Step_02, args: Sequence[Token_Step_02]) -> Token_Step_02:
        tok = self._fresh_token(RECURSIVE_SOURCE, ParserTokenType.S_EXPR, [callee] + list(args))
        tok._s_expr = SExprCall(callee=callee, args=args)
        return tok

    def _make_lambda(self, decl: Sequence[Token_Step_02], body: Token_Step_02) -> Token_Step_02:
        lambda_ident = self._fresh_token("lambda", ParserTokenType.IDENT, [])
        lambda_decl = self._fresh_token(RECURSIVE_SOURCE, ParserTokenType.S_EXPR, list(decl))
        tok = self._fresh_token(RECURSIVE_SOURCE, ParserTokenType.S_EXPR, [lambda_ident, lambda_decl, body])
        tok._s_expr = SExprLambda(args=decl, body=body)
        return tok

    def _make_if(self, cond: Token_Step_02, branch_t: Token_Step_02, branch_f: Token_Step_02) -> Token_Step_02:
        if_ident = self._fresh_token("if", ParserTokenType.IDENT, [])
        tok = self._fresh_token(
            RECURSIVE_SOURCE,
            ParserTokenType.S_EXPR,
            [if_ident, cond, branch_t, branch_f]
        )
        tok._s_expr = SExprIf(cond=cond, branch_t=branch_t, branch_f=branch_f)
        return tok

    def _make_defun(self, symbol: str, decl: Sequence[Token_Step_02], body: Token_Step_02) -> Token_Step_02:
        defun_ident = self._fresh_token("defun", ParserTokenType.IDENT, [])
        defun_symbol_ident = self._fresh_token(symbol, ParserTokenType.IDENT, [])
        defun_decl = self._fresh_token(RECURSIVE_SOURCE, ParserTokenType.S_EXPR, list(decl))
        tok = self._fresh_token(RECURSIVE_SOURCE, ParserTokenType.S_EXPR, [defun_ident, defun_symbol_ident, defun_decl, body])
        tok._s_expr = SExprDefun(symbol=symbol, args=decl, body=body)
        return tok

    def _cps(self, tok: Token_Step_02, k: Token_Step_02) -> Token_Step_02:
        s_expr = tok._s_expr
        if s_expr is None:
            return self._make_call(k, [tok])

        if isinstance(s_expr, SExprFile): return self._cps_file(s_expr, k)
        if isinstance(s_expr, SExprCall):
            if self._is_s_expr_atomic(s_expr):
                return self._cps_atomic(s_expr.callee, s_expr.args, k)
            return self._cps_call(s_expr, k)
        if isinstance(s_expr, SExprLambda): return self._cps_lambda(s_expr, k)
        if isinstance(s_expr, SExprIf): return self._cps_if(s_expr, k)
        if isinstance(s_expr, SExprProgn): return self._cps_progn(s_expr, k)
        if isinstance(s_expr, SExprDefun): return self._cps_defun(s_expr, k)

        return self._make_call(k, [tok])

    def _cps_file(self, s_expr: SExprFile[Token_Step_02], k: Token_Step_02) -> Token_Step_02:
        file_tok = self._fresh_token("file", ParserTokenType.IDENT, [])

        if not s_expr.body:
            nil_tok = self._fresh_token("nil", ParserTokenType.IDENT, [])
            return self._make_call(k, [nil_tok])

        acc = self._cps(s_expr.body[-1], k)
        for t in reversed(s_expr.body[:-1]):
            ign = self._fresh_token(self._next_id("ign"), ParserTokenType.IDENT, [])
            cont = self._make_lambda([ign], acc)
            acc = self._cps(t, cont)
        return self._make_file(file_tok, [acc])

    def _cps_call(self, s_expr: SExprCall[Token_Step_02], k: Token_Step_02) -> Token_Step_02:
        f_src = self._next_id("f")
        f_bind = self._fresh_token(f_src, ParserTokenType.IDENT, [])
        f_use = self._fresh_token(f_src, ParserTokenType.IDENT, [])

        args_srcs = [self._next_id(f"a{i}") for i in range(len(s_expr.args))]
        args_bind = [self._fresh_token(s, ParserTokenType.IDENT, []) for s in args_srcs]
        args_use = [self._fresh_token(s, ParserTokenType.IDENT, []) for s in args_srcs]

        acc = self._make_call(f_use, args_use + [k])

        for i in reversed(range(len(s_expr.args))):
            cont = self._make_lambda([args_bind[i]], acc)
            acc = self._cps(s_expr.args[i], cont)

        f_cont = self._make_lambda([f_bind], acc)
        return self._cps(s_expr.callee, f_cont)

    def _cps_lambda(self, s_expr: SExprLambda[Token_Step_02], k: Token_Step_02) -> Token_Step_02:
        new_k_src = self._next_id("k")
        new_k_bind = self._fresh_token(new_k_src, ParserTokenType.IDENT, [])
        new_k_use = self._fresh_token(new_k_src, ParserTokenType.IDENT, [])

        transformed_body = self._cps(s_expr.body, new_k_use)
        new_decl = [self._fresh_token(arg.source, arg.type, []) for arg in s_expr.args] + [new_k_bind]

        new_lam = self._make_lambda(new_decl, transformed_body)
        return self._make_call(k, [new_lam])

    def _cps_if(self, s_expr: SExprIf[Token_Step_02], k: Token_Step_02) -> Token_Step_02:
        v_src = self._next_id("v")
        v_bind = self._fresh_token(v_src, ParserTokenType.IDENT, [])
        v_use = self._fresh_token(v_src, ParserTokenType.IDENT, [])

        branch_t = self._cps(s_expr.branch_t, k)
        branch_f = self._cps(s_expr.branch_f, k)

        if_tok = self._make_if(v_use, branch_t, branch_f)
        cont = self._make_lambda([v_bind], if_tok)
        return self._cps(s_expr.cond, cont)

    def _cps_progn(self, s_expr: SExprProgn[Token_Step_02], k: Token_Step_02) -> Token_Step_02:
        if not s_expr.body:
            nil_tok = self._fresh_token("nil", ParserTokenType.IDENT, [])
            return self._make_call(k, [nil_tok])

        acc = self._cps(s_expr.body[-1], k)
        for t in reversed(s_expr.body[:-1]):
            ign = self._fresh_token(self._next_id("ign"), ParserTokenType.IDENT, [])
            cont = self._make_lambda([ign], acc)
            acc = self._cps(t, cont)
        return acc

    def _cps_atomic(self, callee: Token_Step_02, operands: Sequence[Token_Step_02], k: Token_Step_02) -> Token_Step_02:
        val_srcs = [self._next_id(f"v{i}") for i in range(len(operands))]
        val_bind = [self._fresh_token(s, ParserTokenType.IDENT, []) for s in val_srcs]
        val_use = [self._fresh_token(s, ParserTokenType.IDENT, []) for s in val_srcs]

        final_op = self._make_call(callee, val_use)
        acc = self._make_call(k, [final_op])

        for i in reversed(range(len(operands))):
            cont = self._make_lambda([val_bind[i]], acc)
            acc = self._cps(operands[i], cont)

        return acc

    def _cps_defun(self, s_expr: SExprDefun[Token_Step_02], k: Token_Step_02) -> Token_Step_02:
        new_k_src = self._next_id("k")
        new_k_bind = self._fresh_token(new_k_src, ParserTokenType.IDENT, [])
        new_k_use = self._fresh_token(new_k_src, ParserTokenType.IDENT, [])

        transformed_body = self._cps(s_expr.body, new_k_use)
        new_decl = [self._fresh_token(arg.source, arg.type, []) for arg in s_expr.args] + [new_k_bind]

        defun_tok = self._make_defun(s_expr.symbol, new_decl, transformed_body)
        return self._make_call(k, [defun_tok])

    def apply(self, root: Token_Step_02) -> Token_Step_02:
        if root._s_expr is None:
            return root

        halt_ident = self._fresh_token("halt", ParserTokenType.IDENT, [])
        return self._cps(root, halt_ident)


def step_03_cps(file_token: Token_Step_02):
    return CPSTransformer().apply(file_token)
