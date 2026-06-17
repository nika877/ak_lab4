"""Семантические S-выражения: распознавание конструкций языка.

После build_tree у нас просто дерево скобок. analyze_s_expr смотрит на
первый идентификатор в списке и создаёт SExprDefun, SExprLambda, SExprIf...
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from enum import Enum, auto
from itertools import chain
from typing import override

from .token_storage import TokenStorage
from .tree import SyntaxToken


class ArithmeticOp(Enum):
    ADD = auto()
    SUB = auto()
    MUL = auto()
    DIV = auto()


class ComparsionOp(Enum):
    EQ = auto()
    NE = auto()
    GT = auto()
    GE = auto()
    LT = auto()
    LE = auto()


class SExprType(Enum):
    DEFUN = auto()
    LAMBDA = auto()
    IF = auto()
    PROGN = auto()


@dataclass(match_args=False)
class BaseSExpr[ParserTokenT](ABC):
    @abstractmethod
    def semantic_children(self) -> Iterator[ParserTokenT]: ...

    @abstractmethod
    def map_tokens[T](self, fn: Callable[[ParserTokenT], T]) -> BaseSExpr[T]: ...


@dataclass
class SExprFile[ParserTokenT](BaseSExpr[ParserTokenT]):
    body: Sequence[ParserTokenT]

    __match_args__ = ("body",)

    @override
    def semantic_children(self) -> Iterator[ParserTokenT]:
        return iter(self.body)

    @override
    def map_tokens[T](self, fn: Callable[[ParserTokenT], T]) -> SExprFile[T]:
        return SExprFile([fn(t) for t in self.body])


@dataclass
class SExprCall[ParserTokenT](BaseSExpr[ParserTokenT]):
    callee: ParserTokenT
    args: Sequence[ParserTokenT]

    __match_args__ = ("callee", "args")

    @override
    def semantic_children(self) -> Iterator[ParserTokenT]:
        return chain(iter([self.callee]), iter(self.args))

    @override
    def map_tokens[T](self, fn: Callable[[ParserTokenT], T]) -> SExprCall[T]:
        return SExprCall(fn(self.callee), [fn(a) for a in self.args])


@dataclass
class SExprDefun[ParserTokenT](BaseSExpr[ParserTokenT]):
    """(defun имя (args...) тело) — именованная функция."""

    symbol: str
    args: Sequence[ParserTokenT]
    body: ParserTokenT

    __match_args__ = ("symbol", "args", "body")

    @override
    def semantic_children(self) -> Iterator[ParserTokenT]:
        return chain(iter(self.args), iter([self.body]))

    @override
    def map_tokens[T](self, fn: Callable[[ParserTokenT], T]) -> SExprDefun[T]:
        return SExprDefun(self.symbol, [fn(a) for a in self.args], fn(self.body))


@dataclass
class SExprLambda[ParserTokenT](BaseSExpr[ParserTokenT]):
    """(lambda (args...) тело) — анонимная функция / замыкание."""

    args: Sequence[ParserTokenT]
    body: ParserTokenT

    __match_args__ = ("args", "body")

    @override
    def semantic_children(self) -> Iterator[ParserTokenT]:
        return chain(iter(self.args), iter([self.body]))

    @override
    def map_tokens[T](self, fn: Callable[[ParserTokenT], T]) -> SExprLambda[T]:
        return SExprLambda([fn(a) for a in self.args], fn(self.body))


@dataclass
class SExprIf[ParserTokenT](BaseSExpr[ParserTokenT]):
    cond: ParserTokenT
    branch_t: ParserTokenT
    branch_f: ParserTokenT

    __match_args__ = ("cond", "branch_t", "branch_f")

    @override
    def semantic_children(self) -> Iterator[ParserTokenT]:
        return iter([self.cond, self.branch_t, self.branch_f])

    @override
    def map_tokens[T](self, fn: Callable[[ParserTokenT], T]) -> SExprIf[T]:
        return SExprIf(fn(self.cond), fn(self.branch_t), fn(self.branch_f))


@dataclass
class SExprProgn[ParserTokenT](BaseSExpr[ParserTokenT]):
    body: Sequence[ParserTokenT]

    __match_args__ = ("body",)

    @override
    def semantic_children(self) -> Iterator[ParserTokenT]:
        return iter(self.body)

    @override
    def map_tokens[T](self, fn: Callable[[ParserTokenT], T]) -> SExprProgn[T]:
        return SExprProgn([fn(t) for t in self.body])


@dataclass
class SExprSetq[ParserTokenT](BaseSExpr[ParserTokenT]):
    """(setq x значение) — мутабельное присваивание (только параметры функции)."""

    target: ParserTokenT
    value: ParserTokenT

    __match_args__ = ("target", "value")

    @override
    def semantic_children(self) -> Iterator[ParserTokenT]:
        return iter([self.target, self.value])

    @override
    def map_tokens[T](self, fn: Callable[[ParserTokenT], T]) -> SExprSetq[T]:
        return SExprSetq(fn(self.target), fn(self.value))


@dataclass
class SExprWhile[ParserTokenT](BaseSExpr[ParserTokenT]):
    cond: ParserTokenT
    body: ParserTokenT

    __match_args__ = ("cond", "body")

    @override
    def semantic_children(self) -> Iterator[ParserTokenT]:
        return iter([self.cond, self.body])

    @override
    def map_tokens[T](self, fn: Callable[[ParserTokenT], T]) -> SExprWhile[T]:
        return SExprWhile(fn(self.cond), fn(self.body))


type SExpr[PT] = (
    SExprFile[PT]
    | SExprCall[PT]
    | SExprDefun[PT]
    | SExprLambda[PT]
    | SExprIf[PT]
    | SExprProgn[PT]
    | SExprSetq[PT]
    | SExprWhile[PT]
)


@dataclass
class SemanticToken(SyntaxToken):
    _s_expr: SExpr[int] | None

    @classmethod
    def from_syntax(cls, token: SyntaxToken, s_expr: SExpr[int] | None) -> SemanticToken:
        return cls(
            _source=token._source,
            type=token.type,
            _children=token._children,
            _s_expr=s_expr,
        )


def analyze_s_expr(storage: TokenStorage[SyntaxToken]):
    """Обойти синтаксическое дерево и прикрепить SExpr к каждому узлу."""
    s_expr_map: dict[int, SExpr[int] | None] = {}

    def traverse(idx: int):
        token = storage.get(idx)
        if not token.is_s_expr:
            s_expr_map[idx] = None
            return

        children = token._children
        first_child = storage.get(children[0])
        if not first_child.is_ident:
            # First child is not an ident keyword — treat as a call (e.g. ((lambda ...) arg))
            for child_idx in children:
                traverse(child_idx)
            s_expr_map[idx] = SExprCall(callee=children[0], args=list(children[1:]))
            return

        first_source = first_child.source

        match first_source:
            case "file":
                for child_idx in children[1:]:
                    traverse(child_idx)
                s_expr_map[idx] = SExprFile(body=list(children[1:]))

            case "defun":
                assert len(children) == 4, "'defun' not valid"
                arglist_children = storage.get(children[2])._children
                for arg_idx in arglist_children:
                    s_expr_map[arg_idx] = None
                traverse(children[3])
                s_expr_map[idx] = SExprDefun(
                    symbol=storage.get(children[1]).source,
                    args=list(arglist_children),
                    body=children[3],
                )

            case "lambda":
                assert len(children) == 3, "'lambda' not valid"
                arglist_children = storage.get(children[1])._children
                for arg_idx in arglist_children:
                    s_expr_map[arg_idx] = None
                traverse(children[2])
                s_expr_map[idx] = SExprLambda(args=list(arglist_children), body=children[2])

            case "if":
                assert len(children) == 4, "'if' not valid"
                for child_idx in children[1:]:
                    traverse(child_idx)
                s_expr_map[idx] = SExprIf(
                    cond=children[1], branch_t=children[2], branch_f=children[3]
                )

            case "progn":
                for child_idx in children[1:]:
                    traverse(child_idx)
                s_expr_map[idx] = SExprProgn(body=list(children[1:]))

            case "setq":
                assert len(children) == 3, "'setq' not valid"
                s_expr_map[children[1]] = None
                traverse(children[2])
                s_expr_map[idx] = SExprSetq(target=children[1], value=children[2])

            case "while":
                assert len(children) == 3, "'while' not valid"
                traverse(children[1])
                traverse(children[2])
                s_expr_map[idx] = SExprWhile(cond=children[1], body=children[2])

            case _:
                for child_idx in children:
                    traverse(child_idx)
                s_expr_map[idx] = SExprCall(callee=children[0], args=list(children[1:]))

    traverse(storage.file_token_idx)

    return storage.promote(lambda token, idx: SemanticToken.from_syntax(token, s_expr_map.get(idx)))
