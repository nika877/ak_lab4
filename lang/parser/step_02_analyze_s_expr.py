from abc import ABC, abstractmethod
from itertools import chain
from typing import Generic, Iterator, Never, Protocol, Self, Sequence, TypeGuard, TypeIs, TypeVar, cast, override, runtime_checkable
from dataclasses import dataclass
from enum import Enum, auto

from .step_01_build_tree import Token_Step_01
from .base_token import ParserToken, ParserTokenT


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
class BaseSExpr(ABC, Generic[ParserTokenT]):
    @abstractmethod
    def semantic_children(self) -> Iterator[ParserTokenT]:
        ...


@dataclass
class SExprFile(BaseSExpr[ParserTokenT], Generic[ParserTokenT]):
    body: Sequence[ParserTokenT]

    __match_args__ = ("body",)

    @override
    def semantic_children(self) -> Iterator[ParserTokenT]:
        return iter(self.body)


@dataclass
class SExprCall(BaseSExpr[ParserTokenT], Generic[ParserTokenT]):
    callee: ParserTokenT
    args: Sequence[ParserTokenT]

    __match_args__ = ("callee", "args")

    @override
    def semantic_children(self) -> Iterator[ParserTokenT]:
        return chain(iter([self.callee]), iter(self.args))


@dataclass
class SExprDefun(BaseSExpr[ParserTokenT], Generic[ParserTokenT]):
    symbol: str
    args: Sequence[ParserTokenT]
    body: ParserTokenT

    __match_args__ = ("symbol", "args", "body")

    @override
    def semantic_children(self) -> Iterator[ParserTokenT]:
        return chain(iter(self.args), iter([self.body]))


@dataclass
class SExprLambda(BaseSExpr[ParserTokenT], Generic[ParserTokenT]):
    args: Sequence[ParserTokenT]
    body: ParserTokenT

    __match_args__ = ("args", "body")

    @override
    def semantic_children(self) -> Iterator[ParserTokenT]:
        return chain(iter(self.args), iter([self.body]))


@dataclass
class SExprIf(BaseSExpr[ParserTokenT], Generic[ParserTokenT]):
    cond: ParserTokenT
    branch_t: ParserTokenT
    branch_f: ParserTokenT

    __match_args__ = ("cond", "branch_t", "branch_f")

    @override
    def semantic_children(self) -> Iterator[ParserTokenT]:
        return iter([self.cond, self.branch_t, self.branch_f])


@dataclass
class SExprProgn(BaseSExpr[ParserTokenT], Generic[ParserTokenT]):
    body: Sequence[ParserTokenT]

    __match_args__ = ("body",)

    @override
    def semantic_children(self) -> Iterator[ParserTokenT]:
        return iter(self.body)


type SExpr[PT: ParserToken] = (
    SExprFile[PT] |
    SExprCall[PT] |
    SExprDefun[PT] |
    SExprLambda[PT] |
    SExprIf[PT] |
    SExprProgn[PT]
)

@dataclass
class Token_Step_02(Token_Step_01):
    _s_expr: SExpr[Self] | None

    def __post_init__(self):
        assert self.is_s_expr == (self.s_expr is not None)

    @property
    def s_expr(self):
        return self._s_expr

    @property
    def children(self) -> Never:
        raise Exception("cannot access children after semantics were analyzed")


def build_token(token: Token_Step_01, s_expr: SExpr[Token_Step_01] | None):
    return token.extend(Token_Step_02, _s_expr=s_expr)


def traverse_argdecl(token: Token_Step_01):
    assert token.is_ident, "non-ident in arglist"
    return build_token(token, None)


def traverse(token: Token_Step_01):
    if not token.is_s_expr:
        return build_token(token, None)

    match token.children[0].source:
        case "file":
            return build_token(
                token,
                SExprFile(
                    list(map(traverse, token.children[1:])),
                )
            )

        case "defun":
            assert len(token.children) == 4, "'defun' not valid"
            return build_token(
                token,
                SExprDefun(
                    token.children[1].source,
                    list(map(traverse_argdecl, token.children[2].children)),
                    traverse(token.children[3])
                )
            )

        case "lambda":
            assert len(token.children) == 3, "'lambda' not valid"
            return build_token(
                token,
                SExprLambda(
                    list(map(traverse_argdecl, token.children[1].children)),
                    traverse(token.children[2])
                )
            )

        case "if":
            assert len(token.children) == 4, "'if' not valid"
            return build_token(
                token,
                SExprIf(
                    traverse(token.children[1]),
                    traverse(token.children[2]),
                    traverse(token.children[3])
                )
            )

        case "progn":
            return build_token(
                token,
                SExprProgn(
                    list(map(traverse, token.children[1].children)),
                )
            )

        case _:
            return build_token(
                token,
                SExprCall(
                    traverse(token.children[0]),
                    list(map(traverse, token.children[1:]))
                )
            )


def step_02_analyze_s_expr(file_token: Token_Step_01):
    return traverse(file_token)
