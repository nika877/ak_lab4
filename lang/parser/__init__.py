"""Парсер: сборка полного пайплайна разбора исходника.

Этапы внутри parse():
  1. build_tree   — токены → синтаксическое дерево (скобки, атомы)
  2. analyze_s_expr — распознать defun, lambda, if, call...
  3. assign_qualnames — имена переменных, области видимости, замыкания
"""

from collections.abc import Iterator
from dataclasses import dataclass

from lang.lexer import LexerToken
from lang.parser.qualname import TreePath

from .cps import cps_transform as cps_transform
from .qualname_assign import (
    FinalToken,
    QualifiedToken,
    assign_qualnames,
)
from .s_expr import analyze_s_expr
from .token_storage import TokenStorage, TokenView
from .tree import build_tree


@dataclass(slots=True)
class ParserResult:
    """Результат парсинга: дерево токенов + мутабельность и автобоксинг."""

    storage: TokenStorage[QualifiedToken]
    all_tokens: dict[TreePath, FinalToken]
    mutable_paths: set[TreePath]      # переменные, изменённые через setq
    autoboxed_paths: set[TreePath]  # мутируемые и захваченные лямбдой → в куче

    @property
    def file_token(self) -> TokenView[QualifiedToken]:
        return self.storage.file_token


def parse(lexer_iter: Iterator[LexerToken]):
    """Разобрать поток токенов в типизированное дерево с именами."""
    syntax_storage = build_tree(lexer_iter)
    semantic_storage = analyze_s_expr(syntax_storage)

    qn_res = assign_qualnames(semantic_storage)

    return ParserResult(
        qn_res.storage,
        qn_res.all_tokens,
        qn_res.mutable_paths,
        qn_res.autoboxed_paths,
    )
