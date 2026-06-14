from typing import ClassVar, Iterator, Self, Sequence, cast
from dataclasses import dataclass
from enum import Enum, auto
from lang.lexer import LexerToken, LexerTokenType
from .base_token import ParserToken


class ParserTokenType(Enum):
    S_EXPR = auto()
    IDENT = auto()
    INTEGER = auto()
    FLOAT = auto()
    STRING = auto()
    BOOLEAN = auto()


class RecursiveSource:
    pass


RECURSIVE_SOURCE = RecursiveSource()


@dataclass
class Token_Step_01(ParserToken["Token_Step_01"]):
    _source: str | RecursiveSource
    type: ParserTokenType
    _children: Sequence[Self]

    @property
    def source(self):
        if isinstance(self._source, RecursiveSource):
            return "(" + " ".join(c.source for c in self._children) + ")"
        assert isinstance(self._source, str)
        return self._source

    @property
    def children(self) -> Sequence[Self]:
        return self._children

    @property
    def is_s_expr(self):
        return self.type == ParserTokenType.S_EXPR

    @property
    def is_ident(self):
        return self.type == ParserTokenType.IDENT

    @property
    def is_integer(self):
        return self.type == ParserTokenType.INTEGER

    @property
    def is_float(self):
        return self.type == ParserTokenType.FLOAT

    @property
    def is_string(self):
        return self.type == ParserTokenType.STRING

    @property
    def is_boolean(self):
        return self.type == ParserTokenType.BOOLEAN


def build_token(source: str | RecursiveSource, type: ParserTokenType, children: list[Token_Step_01]):
    return Token_Step_01(source, type, children)


def step_01_build_tree(lexer_iter: Iterator[LexerToken]) -> Token_Step_01:
    children_stack: list[list[Token_Step_01]] = [[]]

    for token in lexer_iter:
        if token.ty == LexerTokenType.OPEN_PARENTHESES:
            children_stack.append([])

        elif token.ty == LexerTokenType.CLOSED_PARENTHESES:
            if len(children_stack) == 1:
                raise Exception("mismatched ')'")

            children = children_stack.pop()
            p_token = build_token(RECURSIVE_SOURCE, ParserTokenType.S_EXPR, children)
            children_stack[-1].append(p_token)

        elif token.ty == LexerTokenType.EOF:
            if len(children_stack) != 1:
                raise Exception("unclosed '('")

            children = children_stack.pop()
            children.insert(0, build_token(
                "file",
                ParserTokenType.IDENT,
                []
            ))
            return build_token(RECURSIVE_SOURCE, ParserTokenType.S_EXPR, children)

        elif token.ty == LexerTokenType.IDENT:
            children_stack[-1].append(build_token(token.source, ParserTokenType.IDENT, []))

        elif token.ty == LexerTokenType.INTEGER:
            children_stack[-1].append(build_token(token.source, ParserTokenType.INTEGER, []))

        elif token.ty == LexerTokenType.STRING:
            children_stack[-1].append(build_token(token.source, ParserTokenType.STRING, []))

        elif token.ty == LexerTokenType.BOOLEAN:
            children_stack[-1].append(build_token(token.source, ParserTokenType.BOOLEAN, []))

        else:
            raise Exception(token.ty.name)

    raise RuntimeError("no EOF in lexer output")
