"""Хранилище токенов и «вид» на один узел дерева (TokenView)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from lang.parser.qualname import QualName

from .tree import ParserTokenType, RecursiveSource, SyntaxToken


@dataclass
class TokenStorage[TokenT: SyntaxToken]:
    """Массив всех токенов программы + индекс корневого (file)."""

    _tokens: list[TokenT]
    _file_token_idx: int

    def __len__(self) -> int:
        return len(self._tokens)

    def get(self, idx: int) -> TokenT:
        return self._tokens[idx]

    def add(self, token: TokenT) -> int:
        idx = len(self._tokens)
        self._tokens.append(token)
        return idx

    def view(self, idx: int) -> TokenView[TokenT]:
        return TokenView(self, idx)

    @property
    def file_token_idx(self) -> int:
        return self._file_token_idx

    @property
    def file_token(self) -> TokenView[TokenT]:
        return self.view(self._file_token_idx)

    def promote[NewTokenT: SyntaxToken](
        self, promoter: Callable[[TokenT, int], NewTokenT]
    ) -> TokenStorage[NewTokenT]:
        new_tokens = [promoter(tok, i) for i, tok in enumerate(self._tokens)]
        self._tokens.clear()
        return TokenStorage(new_tokens, self._file_token_idx)


@dataclass
class TokenView[TokenT: SyntaxToken]:
    """Обёртка над одним токеном: удобный доступ к детям, source, s_expr."""

    _storage: TokenStorage[TokenT]
    _index: int

    @property
    def index(self) -> int:
        return self._index

    @property
    def token(self) -> TokenT:
        return self._storage.get(self._index)

    @property
    def source(self) -> str:
        tok = self.token
        if isinstance(tok._source, RecursiveSource):
            return "(" + " ".join(self._storage.view(i).source for i in tok._children) + ")"
        return tok._source

    @property
    def type(self) -> ParserTokenType:
        return self.token.type

    @property
    def is_s_expr(self) -> bool:
        return self.token.type == ParserTokenType.S_EXPR

    @property
    def is_ident(self) -> bool:
        return self.token.type == ParserTokenType.IDENT

    @property
    def is_integer(self) -> bool:
        return self.token.type == ParserTokenType.INTEGER

    @property
    def is_float(self) -> bool:
        return self.token.type == ParserTokenType.FLOAT

    @property
    def is_double(self) -> bool:
        return self.token.type == ParserTokenType.DOUBLE

    @property
    def is_string(self) -> bool:
        return self.token.type == ParserTokenType.STRING

    @property
    def is_boolean(self) -> bool:
        return self.token.type == ParserTokenType.BOOLEAN

    @property
    def children(self) -> list[TokenView[TokenT]]:
        return [self._storage.view(i) for i in self.token._children]

    @property
    def s_expr(self):
        raw = getattr(self.token, "_s_expr", None)
        if raw is None:
            return None
        return raw.map_tokens(lambda idx: self._storage.view(idx))

    @property
    def qualname(self):
        token = self.token
        if hasattr(token, "qualname"):
            return token.qualname
        raise Exception("Cannot access qualname yet")

    @qualname.setter
    def qualname(self, value: QualName) -> None:
        token = self.token
        if hasattr(token, "qualname"):
            token.qualname = value
            return
        raise Exception("Cannot access qualname yet")
