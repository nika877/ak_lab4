from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum, auto

from lang.exceptions import ParserError
from lang.lexer import LexerToken, LexerTokenType


class ParserTokenType(Enum):
    S_EXPR = auto()
    IDENT = auto()
    INTEGER = auto()
    FLOAT = auto()
    DOUBLE = auto()
    STRING = auto()
    BOOLEAN = auto()


class RecursiveSource:
    pass


RECURSIVE_SOURCE = RecursiveSource()


@dataclass
class SyntaxToken:
    _source: str | RecursiveSource
    type: ParserTokenType
    _children: list[int]

    @property
    def source(self) -> str:
        assert isinstance(self._source, str)
        return self._source

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
    def is_double(self):
        return self.type == ParserTokenType.DOUBLE

    @property
    def is_string(self):
        return self.type == ParserTokenType.STRING

    @property
    def is_boolean(self):
        return self.type == ParserTokenType.BOOLEAN


def build_tree(lexer_iter: Iterator[LexerToken]):
    from .token_storage import TokenStorage

    storage: TokenStorage[SyntaxToken] = TokenStorage([], -1)

    def add_token(source: str | RecursiveSource, type: ParserTokenType, children: list[int]) -> int:
        return storage.add(SyntaxToken(source, type, children))

    children_stack: list[list[int]] = [[]]

    for token in lexer_iter:
        if token.ty == LexerTokenType.OPEN_PARENTHESES:
            children_stack.append([])

        elif token.ty == LexerTokenType.CLOSED_PARENTHESES:
            if len(children_stack) == 1:
                raise ParserError("mismatched ')'")

            children = children_stack.pop()
            idx = add_token(RECURSIVE_SOURCE, ParserTokenType.S_EXPR, children)
            children_stack[-1].append(idx)

        elif token.ty == LexerTokenType.EOF:
            if len(children_stack) != 1:
                raise ParserError("unclosed '('")

            children = children_stack.pop()
            file_kw = add_token("file", ParserTokenType.IDENT, [])
            children.insert(0, file_kw)
            file_idx = add_token(RECURSIVE_SOURCE, ParserTokenType.S_EXPR, children)
            storage._file_token_idx = file_idx
            return storage

        elif token.ty == LexerTokenType.IDENT:
            children_stack[-1].append(add_token(token.source, ParserTokenType.IDENT, []))

        elif token.ty == LexerTokenType.INTEGER:
            children_stack[-1].append(add_token(token.source, ParserTokenType.INTEGER, []))

        elif token.ty == LexerTokenType.FLOAT:
            children_stack[-1].append(add_token(token.source, ParserTokenType.FLOAT, []))

        elif token.ty == LexerTokenType.DOUBLE:
            children_stack[-1].append(add_token(token.source, ParserTokenType.DOUBLE, []))

        elif token.ty == LexerTokenType.STRING:
            children_stack[-1].append(add_token(token.source, ParserTokenType.STRING, []))

        elif token.ty == LexerTokenType.BOOLEAN:
            children_stack[-1].append(add_token(token.source, ParserTokenType.BOOLEAN, []))

        else:
            raise ParserError(token.ty.name)

    raise ParserError("no EOF in lexer output")
