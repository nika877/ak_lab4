"""CPS-трансформация (Continuation-Passing Style).

Весь код переписывается так, что «что делать дальше» передаётся явно
как аргумент k (continuation). Например, (+ 1 2) становится цепочкой
вызовов, где каждый шаг получает k — куда передать результат.

Нужно для единообразной компиляции вызовов и встроенных функций.
"""

from collections.abc import Sequence

from .qualname import BuiltinQualName
from .qualname_assign import QualifiedToken
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
from .token_storage import TokenStorage
from .tree import (
    RECURSIVE_SOURCE,
    ParserTokenType,
    RecursiveSource,
)


class CPSTransformer:
    """Преобразует дерево в CPS: добавляет лямбды-продолжения и вызовы k."""

    def __init__(self, input_storage: TokenStorage[QualifiedToken]) -> None:
        self._input = input_storage
        self._output: TokenStorage[SemanticToken] = TokenStorage([], -1)
        self._counter = 0

    def _next_id(self, prefix: str) -> str:
        val = f"{prefix}{self._counter}"
        self._counter += 1
        return val

    def _import_leaf(self, input_idx: int) -> int:
        t = self._input.get(input_idx)
        return self._output.add(SemanticToken(t._source, t.type, [], None))

    def _fresh_token(
        self,
        source: str | RecursiveSource,
        type: ParserTokenType,
        children: list[int],
    ) -> int:
        return self._output.add(SemanticToken(source, type, children, None))

    def _make_file(self, callee_idx: int, body: list[int]) -> int:
        idx = self._fresh_token(RECURSIVE_SOURCE, ParserTokenType.S_EXPR, [callee_idx] + body)
        self._output.get(idx)._s_expr = SExprFile(body=body)
        return idx

    def _make_call(self, callee: int, args: list[int]) -> int:
        idx = self._fresh_token(RECURSIVE_SOURCE, ParserTokenType.S_EXPR, [callee] + args)
        self._output.get(idx)._s_expr = SExprCall(callee=callee, args=args)
        return idx

    def _make_lambda(self, decl: list[int], body: int) -> int:
        lambda_ident = self._fresh_token("lambda", ParserTokenType.IDENT, [])
        lambda_decl = self._fresh_token(RECURSIVE_SOURCE, ParserTokenType.S_EXPR, list(decl))
        idx = self._fresh_token(
            RECURSIVE_SOURCE, ParserTokenType.S_EXPR, [lambda_ident, lambda_decl, body]
        )
        self._output.get(idx)._s_expr = SExprLambda(args=decl, body=body)
        return idx

    def _make_if(self, cond: int, branch_t: int, branch_f: int) -> int:
        if_ident = self._fresh_token("if", ParserTokenType.IDENT, [])
        idx = self._fresh_token(
            RECURSIVE_SOURCE, ParserTokenType.S_EXPR, [if_ident, cond, branch_t, branch_f]
        )
        self._output.get(idx)._s_expr = SExprIf(cond=cond, branch_t=branch_t, branch_f=branch_f)
        return idx

    def _make_defun(self, symbol: str, decl: list[int], body: int) -> int:
        defun_ident = self._fresh_token("defun", ParserTokenType.IDENT, [])
        defun_symbol_ident = self._fresh_token(symbol, ParserTokenType.IDENT, [])
        defun_decl = self._fresh_token(RECURSIVE_SOURCE, ParserTokenType.S_EXPR, list(decl))
        idx = self._fresh_token(
            RECURSIVE_SOURCE,
            ParserTokenType.S_EXPR,
            [defun_ident, defun_symbol_ident, defun_decl, body],
        )
        self._output.get(idx)._s_expr = SExprDefun(symbol=symbol, args=decl, body=body)
        return idx

    def _make_setq(self, target: int, value: int) -> int:
        setq_ident = self._fresh_token("setq", ParserTokenType.IDENT, [])
        idx = self._fresh_token(
            RECURSIVE_SOURCE, ParserTokenType.S_EXPR, [setq_ident, target, value]
        )
        self._output.get(idx)._s_expr = SExprSetq(target=target, value=value)
        return idx

    def _make_while(self, cond: int, body: int) -> int:
        while_ident = self._fresh_token("while", ParserTokenType.IDENT, [])
        idx = self._fresh_token(RECURSIVE_SOURCE, ParserTokenType.S_EXPR, [while_ident, cond, body])
        self._output.get(idx)._s_expr = SExprWhile(cond=cond, body=body)
        return idx

    def _make_progn(self, body: list[int]) -> int:
        progn_ident = self._fresh_token("progn", ParserTokenType.IDENT, [])
        idx = self._fresh_token(RECURSIVE_SOURCE, ParserTokenType.S_EXPR, [progn_ident] + body)
        self._output.get(idx)._s_expr = SExprProgn(body=body)
        return idx

    def _is_s_expr_atomic(self, s_expr: SExprCall[int]) -> bool:
        callee_tok = self._input.get(s_expr.callee)
        if isinstance(callee_tok, QualifiedToken) and isinstance(
            callee_tok.qualname, BuiltinQualName
        ):
            return callee_tok.qualname.symbol.is_atomic
        return False

    def _wrap_atomic_as_lambda(self, input_idx: int, k: int) -> int:
        from lang.lang_type import FunctionLanguageType, LanguageTypeVar

        tok = self._input.get(input_idx)
        assert isinstance(tok, QualifiedToken) and isinstance(tok.qualname, BuiltinQualName)
        symbol = tok.qualname.symbol
        lt = symbol.lang_type_builder(lambda: LanguageTypeVar(self._next_id("_arity")))
        assert isinstance(lt, FunctionLanguageType)
        arity = len(lt.arg_types)

        arg_srcs = [self._next_id("a") for _ in range(arity)]
        args_bind = [self._fresh_token(s, ParserTokenType.IDENT, []) for s in arg_srcs]
        args_use = [self._fresh_token(s, ParserTokenType.IDENT, []) for s in arg_srcs]

        k_inner_src = self._next_id("k")
        k_inner_bind = self._fresh_token(k_inner_src, ParserTokenType.IDENT, [])
        k_inner_use = self._fresh_token(k_inner_src, ParserTokenType.IDENT, [])

        callee = self._fresh_token(tok.source, ParserTokenType.IDENT, [])

        atomic_call = self._make_call(callee, args_use)
        body = self._make_call(k_inner_use, [atomic_call])

        wrapper = self._make_lambda(args_bind + [k_inner_bind], body)
        return self._make_call(k, [wrapper])

    def _passthrough(self, input_idx: int) -> int:
        input_token = self._input.get(input_idx)
        s_expr = input_token._s_expr

        if s_expr is None:
            return self._import_leaf(input_idx)

        if isinstance(s_expr, SExprCall):
            new_callee = self._passthrough(s_expr.callee)
            new_args = [self._passthrough(a) for a in s_expr.args]
            return self._make_call(new_callee, new_args)
        if isinstance(s_expr, SExprIf):
            return self._make_if(
                self._passthrough(s_expr.cond),
                self._passthrough(s_expr.branch_t),
                self._passthrough(s_expr.branch_f),
            )
        if isinstance(s_expr, SExprSetq):
            return self._make_setq(
                self._passthrough(s_expr.target),
                self._passthrough(s_expr.value),
            )
        if isinstance(s_expr, SExprWhile):
            return self._make_while(
                self._passthrough(s_expr.cond),
                self._passthrough(s_expr.body),
            )
        if isinstance(s_expr, SExprProgn):
            return self._make_progn([self._passthrough(t) for t in s_expr.body])

        return self._import_leaf(input_idx)

    def _cps_setq(self, s_expr: SExprSetq[int], k: int) -> int:
        val_src = self._next_id("v")
        val_bind = self._fresh_token(val_src, ParserTokenType.IDENT, [])
        val_use = self._fresh_token(val_src, ParserTokenType.IDENT, [])
        target = self._import_leaf(s_expr.target)
        setq_node = self._make_setq(target, val_use)
        body = self._make_call(k, [setq_node])
        cont = self._make_lambda([val_bind], body)
        return self._cps(s_expr.value, cont)

    def _cps_while(self, s_expr: SExprWhile[int], k: int) -> int:
        new_cond = self._passthrough(s_expr.cond)
        new_body = self._passthrough(s_expr.body)
        while_idx = self._make_while(new_cond, new_body)
        return self._make_call(k, [while_idx])

    def _cps(self, input_idx: int, k: int) -> int:
        input_token = self._input.get(input_idx)
        s_expr = input_token._s_expr

        if s_expr is None:
            if (
                isinstance(input_token, QualifiedToken)
                and isinstance(input_token.qualname, BuiltinQualName)
                and input_token.qualname.symbol.is_atomic
            ):
                return self._wrap_atomic_as_lambda(input_idx, k)
            return self._make_call(k, [self._import_leaf(input_idx)])

        if isinstance(s_expr, SExprFile):
            return self._cps_file(s_expr, k)
        if isinstance(s_expr, SExprCall):
            if self._is_s_expr_atomic(s_expr):
                return self._cps_atomic(s_expr.callee, s_expr.args, k)
            return self._cps_call(s_expr, k)
        if isinstance(s_expr, SExprLambda):
            return self._cps_lambda(s_expr, k)
        if isinstance(s_expr, SExprIf):
            return self._cps_if(s_expr, k)
        if isinstance(s_expr, SExprProgn):
            return self._cps_progn(s_expr, k)
        if isinstance(s_expr, SExprDefun):
            return self._cps_defun(s_expr, k)
        if isinstance(s_expr, SExprSetq):
            return self._cps_setq(s_expr, k)
        if isinstance(s_expr, SExprWhile):
            return self._cps_while(s_expr, k)

        return self._make_call(k, [self._import_leaf(input_idx)])

    def _cps_file(self, s_expr: SExprFile[int], k: int) -> int:
        file_tok = self._fresh_token("file", ParserTokenType.IDENT, [])

        if not s_expr.body:
            nil_tok = self._fresh_token("nil", ParserTokenType.IDENT, [])
            return self._make_call(k, [nil_tok])

        acc = self._cps(s_expr.body[-1], k)
        for t_idx in reversed(s_expr.body[:-1]):
            ign = self._fresh_token(self._next_id("ign"), ParserTokenType.IDENT, [])
            cont = self._make_lambda([ign], acc)
            acc = self._cps(t_idx, cont)
        return self._make_file(file_tok, [acc])

    def _cps_call(self, s_expr: SExprCall[int], k: int) -> int:
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

    def _cps_lambda(self, s_expr: SExprLambda[int], k: int) -> int:
        new_k_src = self._next_id("k")
        new_k_bind = self._fresh_token(new_k_src, ParserTokenType.IDENT, [])
        new_k_use = self._fresh_token(new_k_src, ParserTokenType.IDENT, [])

        transformed_body = self._cps(s_expr.body, new_k_use)
        new_decl = [
            self._fresh_token(self._input.get(arg_idx).source, self._input.get(arg_idx).type, [])
            for arg_idx in s_expr.args
        ] + [new_k_bind]

        new_lam = self._make_lambda(new_decl, transformed_body)
        return self._make_call(k, [new_lam])

    def _cps_if(self, s_expr: SExprIf[int], k: int) -> int:
        v_src = self._next_id("v")
        v_bind = self._fresh_token(v_src, ParserTokenType.IDENT, [])
        v_use = self._fresh_token(v_src, ParserTokenType.IDENT, [])

        branch_t = self._cps(s_expr.branch_t, k)
        branch_f = self._cps(s_expr.branch_f, k)

        if_tok = self._make_if(v_use, branch_t, branch_f)
        cont = self._make_lambda([v_bind], if_tok)
        return self._cps(s_expr.cond, cont)

    def _cps_progn(self, s_expr: SExprProgn[int], k: int) -> int:
        if not s_expr.body:
            nil_tok = self._fresh_token("nil", ParserTokenType.IDENT, [])
            return self._make_call(k, [nil_tok])

        acc = self._cps(s_expr.body[-1], k)
        for t_idx in reversed(s_expr.body[:-1]):
            ign = self._fresh_token(self._next_id("ign"), ParserTokenType.IDENT, [])
            cont = self._make_lambda([ign], acc)
            acc = self._cps(t_idx, cont)
        return acc

    def _cps_atomic(self, callee_idx: int, operands: Sequence[int], k: int) -> int:
        val_srcs = [self._next_id(f"v{i}") for i in range(len(operands))]
        val_bind = [self._fresh_token(s, ParserTokenType.IDENT, []) for s in val_srcs]
        val_use = [self._fresh_token(s, ParserTokenType.IDENT, []) for s in val_srcs]

        callee_out = self._import_leaf(callee_idx)
        final_op = self._make_call(callee_out, val_use)
        acc = self._make_call(k, [final_op])

        for i in reversed(range(len(operands))):
            cont = self._make_lambda([val_bind[i]], acc)
            acc = self._cps(operands[i], cont)

        return acc

    def _cps_defun(self, s_expr: SExprDefun[int], k: int) -> int:
        new_k_src = self._next_id("k")
        new_k_bind = self._fresh_token(new_k_src, ParserTokenType.IDENT, [])
        new_k_use = self._fresh_token(new_k_src, ParserTokenType.IDENT, [])

        transformed_body = self._cps(s_expr.body, new_k_use)
        new_decl = [
            self._fresh_token(self._input.get(arg_idx).source, self._input.get(arg_idx).type, [])
            for arg_idx in s_expr.args
        ] + [new_k_bind]

        defun_tok = self._make_defun(s_expr.symbol, new_decl, transformed_body)
        return self._make_call(k, [defun_tok])

    def apply(self) -> TokenStorage[SemanticToken]:
        halt = self._fresh_token("halt", ParserTokenType.IDENT, [])
        file_idx = self._cps(self._input.file_token_idx, halt)
        self._output._file_token_idx = file_idx
        return self._output


class CPSSimplifier:
    def __init__(self, storage: TokenStorage[SemanticToken]) -> None:
        self._storage = storage
        self._counter = 0
        self._changed = False

    def _next_id(self, prefix: str) -> str:
        val = f"{prefix}{self._counter}"
        self._counter += 1
        return val

    def _fresh_token(
        self,
        source: str | RecursiveSource,
        type: ParserTokenType,
        children: list[int],
    ) -> int:
        return self._storage.add(SemanticToken(source, type, children, None))

    def _clone_token(self, idx: int) -> int:
        tok = self._storage.get(idx)
        new_children = [self._clone_token(c) for c in tok._children]
        new_tok = SemanticToken(tok._source, tok.type, new_children, None)
        new_idx = self._storage.add(new_tok)

        if tok._s_expr is not None:
            s = tok._s_expr
            if isinstance(s, SExprCall):
                child_map = dict(zip(tok._children, new_children, strict=True))
                new_tok._s_expr = SExprCall(
                    callee=child_map[s.callee],
                    args=[child_map[a] for a in s.args],
                )
            elif isinstance(s, SExprLambda):
                child_map = dict(zip(tok._children, new_children, strict=True))
                new_tok._s_expr = SExprLambda(
                    args=[child_map[a] for a in s.args],
                    body=child_map[s.body],
                )
            elif isinstance(s, SExprIf):
                child_map = dict(zip(tok._children, new_children, strict=True))
                new_tok._s_expr = SExprIf(
                    cond=child_map[s.cond],
                    branch_t=child_map[s.branch_t],
                    branch_f=child_map[s.branch_f],
                )
            elif isinstance(s, (SExprFile, SExprProgn)):
                child_map = dict(zip(tok._children, new_children, strict=True))
                new_tok._s_expr = type(s)(body=[child_map[b] for b in s.body])
            elif isinstance(s, SExprDefun):
                child_map = dict(zip(tok._children, new_children, strict=True))
                param_list_tok = self._storage.get(new_children[2])
                new_tok._s_expr = SExprDefun(
                    symbol=s.symbol,
                    args=list(param_list_tok._children),
                    body=child_map[s.body],
                )
            elif isinstance(s, SExprSetq):
                child_map = dict(zip(tok._children, new_children, strict=True))
                new_tok._s_expr = SExprSetq(
                    target=child_map[s.target],
                    value=child_map[s.value],
                )
            elif isinstance(s, SExprWhile):
                child_map = dict(zip(tok._children, new_children, strict=True))
                new_tok._s_expr = SExprWhile(
                    cond=child_map[s.cond],
                    body=child_map[s.body],
                )

        return new_idx

    def _make_call(self, callee: int, args: list[int]) -> int:
        idx = self._fresh_token(RECURSIVE_SOURCE, ParserTokenType.S_EXPR, [callee] + args)
        self._storage.get(idx)._s_expr = SExprCall(callee=callee, args=args)
        return idx

    def _make_lambda(self, decl: list[int], body: int) -> int:
        lam_ident = self._fresh_token("lambda", ParserTokenType.IDENT, [])
        idx = self._fresh_token(
            RECURSIVE_SOURCE, ParserTokenType.S_EXPR, [lam_ident] + decl + [body]
        )
        self._storage.get(idx)._s_expr = SExprLambda(args=decl, body=body)
        return idx

    def _make_if(self, cond: int, branch_t: int, branch_f: int) -> int:
        if_ident = self._fresh_token("if", ParserTokenType.IDENT, [])
        idx = self._fresh_token(
            RECURSIVE_SOURCE, ParserTokenType.S_EXPR, [if_ident, cond, branch_t, branch_f]
        )
        self._storage.get(idx)._s_expr = SExprIf(cond=cond, branch_t=branch_t, branch_f=branch_f)
        return idx

    def _make_file(self, body: list[int]) -> int:
        file_ident = self._fresh_token("file", ParserTokenType.IDENT, [])
        idx = self._fresh_token(RECURSIVE_SOURCE, ParserTokenType.S_EXPR, [file_ident] + body)
        self._storage.get(idx)._s_expr = SExprFile(body=body)
        return idx

    def _make_progn(self, body: list[int]) -> int:
        progn_ident = self._fresh_token("progn", ParserTokenType.IDENT, [])
        idx = self._fresh_token(RECURSIVE_SOURCE, ParserTokenType.S_EXPR, [progn_ident] + body)
        self._storage.get(idx)._s_expr = SExprProgn(body=body)
        return idx

    def _make_defun(self, symbol: str, decl: list[int], body: int) -> int:
        defun_ident = self._fresh_token("defun", ParserTokenType.IDENT, [])
        sym_ident = self._fresh_token(symbol, ParserTokenType.IDENT, [])
        decl_list = self._fresh_token(RECURSIVE_SOURCE, ParserTokenType.S_EXPR, list(decl))
        idx = self._fresh_token(
            RECURSIVE_SOURCE, ParserTokenType.S_EXPR, [defun_ident, sym_ident, decl_list, body]
        )
        self._storage.get(idx)._s_expr = SExprDefun(symbol=symbol, args=list(decl), body=body)
        return idx

    def _make_setq(self, target: int, value: int) -> int:
        setq_ident = self._fresh_token("setq", ParserTokenType.IDENT, [])
        idx = self._fresh_token(
            RECURSIVE_SOURCE, ParserTokenType.S_EXPR, [setq_ident, target, value]
        )
        self._storage.get(idx)._s_expr = SExprSetq(target=target, value=value)
        return idx

    def _make_while(self, cond: int, body: int) -> int:
        while_ident = self._fresh_token("while", ParserTokenType.IDENT, [])
        idx = self._fresh_token(RECURSIVE_SOURCE, ParserTokenType.S_EXPR, [while_ident, cond, body])
        self._storage.get(idx)._s_expr = SExprWhile(cond=cond, body=body)
        return idx

    def _is_admin_lambda(self, lam: SExprLambda[int]) -> bool:
        return any(
            self._storage.get(p).source.startswith(("v", "a", "ign", "f", "k")) for p in lam.args
        )

    def _is_eta_reducible(self, lam: SExprLambda[int], body_idx: int) -> bool:
        body_tok = self._storage.get(body_idx)
        if not isinstance(body_tok._s_expr, SExprCall):
            return False
        call = body_tok._s_expr
        if len(lam.args) != 1 or len(call.args) != 1:
            return False
        lam_arg_tok = self._storage.get(lam.args[0])
        call_arg_tok = self._storage.get(call.args[0])
        callee_tok = self._storage.get(call.callee)
        if lam_arg_tok.is_s_expr or call_arg_tok.is_s_expr or callee_tok.is_s_expr:
            return False
        return lam_arg_tok.source == call_arg_tok.source and callee_tok.source != lam_arg_tok.source

    def _substitute(self, node_idx: int, target: str, replacement_idx: int) -> int:
        tok = self._storage.get(node_idx)
        if tok.type == ParserTokenType.IDENT and tok.source == target:
            return self._clone_token(replacement_idx)
        if tok._s_expr is None:
            return node_idx

        s = tok._s_expr
        if isinstance(s, SExprCall):
            return self._make_call(
                self._substitute(s.callee, target, replacement_idx),
                [self._substitute(a, target, replacement_idx) for a in s.args],
            )
        elif isinstance(s, SExprLambda):
            if any(self._storage.get(a).source == target for a in s.args):
                return node_idx
            return self._make_lambda(
                list(s.args), self._substitute(s.body, target, replacement_idx)
            )
        elif isinstance(s, SExprIf):
            return self._make_if(
                self._substitute(s.cond, target, replacement_idx),
                self._substitute(s.branch_t, target, replacement_idx),
                self._substitute(s.branch_f, target, replacement_idx),
            )
        elif isinstance(s, SExprFile):
            return self._make_file([self._substitute(t, target, replacement_idx) for t in s.body])
        elif isinstance(s, SExprProgn):
            return self._make_progn([self._substitute(t, target, replacement_idx) for t in s.body])
        elif isinstance(s, SExprDefun):
            if any(self._storage.get(a).source == target for a in s.args):
                return node_idx
            return self._make_defun(
                s.symbol, list(s.args), self._substitute(s.body, target, replacement_idx)
            )
        elif isinstance(s, SExprSetq):
            return self._make_setq(
                s.target,
                self._substitute(s.value, target, replacement_idx),
            )
        elif isinstance(s, SExprWhile):
            return self._make_while(
                self._substitute(s.cond, target, replacement_idx),
                self._substitute(s.body, target, replacement_idx),
            )
        return node_idx

    def _is_mutated_in(self, var_source: str, node_idx: int) -> bool:
        """True, если где-то в поддереве встречается `(setq var_source ...)`."""
        tok = self._storage.get(node_idx)
        s = tok._s_expr
        if isinstance(s, SExprSetq):
            target_tok = self._storage.get(s.target)
            if target_tok.type == ParserTokenType.IDENT and target_tok.source == var_source:
                return True
        if s is None:
            return False
        if isinstance(s, SExprLambda):
            if any(self._storage.get(a).source == var_source for a in s.args):
                return False
            return self._is_mutated_in(var_source, s.body)
        if isinstance(s, SExprCall):
            if self._is_mutated_in(var_source, s.callee):
                return True
            return any(self._is_mutated_in(var_source, a) for a in s.args)
        if isinstance(s, SExprIf):
            return (
                self._is_mutated_in(var_source, s.cond)
                or self._is_mutated_in(var_source, s.branch_t)
                or self._is_mutated_in(var_source, s.branch_f)
            )
        if isinstance(s, (SExprFile, SExprProgn)):
            return any(self._is_mutated_in(var_source, t) for t in s.body)
        if isinstance(s, SExprDefun):
            if any(self._storage.get(a).source == var_source for a in s.args):
                return False
            return self._is_mutated_in(var_source, s.body)
        if isinstance(s, SExprSetq):
            return self._is_mutated_in(var_source, s.value)
        if isinstance(s, SExprWhile):
            return self._is_mutated_in(var_source, s.cond) or self._is_mutated_in(
                var_source, s.body
            )
        return False

    def _transform(self, node_idx: int) -> int:
        tok = self._storage.get(node_idx)
        if tok._s_expr is None:
            return node_idx

        s = tok._s_expr
        if isinstance(s, SExprCall):
            new_callee = self._transform(s.callee)
            new_args = [self._transform(a) for a in s.args]

            callee_tok = self._storage.get(new_callee)
            if isinstance(callee_tok._s_expr, SExprLambda):
                lam = callee_tok._s_expr
                if self._is_admin_lambda(lam) and len(lam.args) == len(new_args):
                    if any(self._storage.get(p).source.startswith("ign") for p in lam.args):
                        return self._make_call(new_callee, new_args)

                    if any(
                        self._is_mutated_in(self._storage.get(p).source, lam.body) for p in lam.args
                    ):
                        return self._make_call(new_callee, new_args)

                    self._changed = True
                    result = lam.body
                    for param_idx, arg_idx in zip(lam.args, new_args, strict=True):
                        result = self._substitute(
                            result, self._storage.get(param_idx).source, arg_idx
                        )
                    return self._transform(result)
            return self._make_call(new_callee, new_args)

        elif isinstance(s, SExprLambda):
            new_body = self._transform(s.body)
            if self._is_eta_reducible(s, new_body):
                self._changed = True
                body_tok = self._storage.get(new_body)
                assert isinstance(body_tok._s_expr, SExprCall)
                return body_tok._s_expr.callee
            return self._make_lambda(list(s.args), new_body)

        elif isinstance(s, SExprIf):
            return self._make_if(
                self._transform(s.cond),
                self._transform(s.branch_t),
                self._transform(s.branch_f),
            )
        elif isinstance(s, SExprFile):
            return self._make_file([self._transform(t) for t in s.body])
        elif isinstance(s, SExprProgn):
            return self._make_progn([self._transform(t) for t in s.body])
        elif isinstance(s, SExprDefun):
            new_args = [self._clone_token(a) for a in s.args]
            return self._make_defun(s.symbol, new_args, self._transform(s.body))
        elif isinstance(s, SExprSetq):
            return self._make_setq(
                self._transform(s.target),
                self._transform(s.value),
            )
        elif isinstance(s, SExprWhile):
            return self._make_while(
                self._transform(s.cond),
                self._transform(s.body),
            )
        return node_idx

    def apply(self):
        while True:
            self._changed = False
            new_file = self._transform(self._storage.file_token_idx)
            self._storage._file_token_idx = new_file
            if not self._changed:
                break

        self._storage._file_token_idx = self._clone_token(self._storage.file_token_idx)


def cps_transform(input_storage: TokenStorage[QualifiedToken]) -> TokenStorage[SemanticToken]:
    """Публичная точка входа CPS: преобразование + упрощение дерева."""
    output = CPSTransformer(input_storage).apply()
    CPSSimplifier(output).apply()
    return output
