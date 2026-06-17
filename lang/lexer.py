"""Лексер (лексический анализатор) для диалекта Lisp.

Разбивает исходный текст на токены: скобки, числа, строки, идентификаторы.
Следующий этап — парсер (tree.py), который из токенов строит дерево S-выражений.
"""

import re
from dataclasses import dataclass
from enum import Enum, auto


class LexerTokenType(Enum):
    """Типы токенов, которые выдаёт лексер."""

    OPEN_PARENTHESES = auto()   # (
    CLOSED_PARENTHESES = auto() # )
    FLOAT = auto()              # 3.14
    DOUBLE = auto()             # 3.14d
    INTEGER = auto()            # 42, -7
    BOOLEAN = auto()            # true, false
    IDENT = auto()              # имя переменной или ключевое слово
    STRING = auto()             # "текст"
    UNDEFINED = auto()          # неизвестный символ (ошибка)
    SKIP = auto()               # пробелы и переводы строк (пропускаем)
    EOF = auto()                # конец файла


@dataclass(frozen=True, slots=True)
class LexerToken:
    """Один токен: его тип и исходный текст (как в файле)."""

    ty: LexerTokenType
    source: str


def tokenize(source: str):
    """Разбить исходный текст на поток токенов (генератор).

    Использует регулярные выражения: для каждого совпадения определяет тип
    токена по имени группы в regex. Пробелы пропускаются, в конце — EOF.
    """
    # Порядок важен: DOUBLE раньше FLOAT, FLOAT раньше INTEGER
    token_spec = [
        ("OPEN_PARENTHESES", r"\("),
        ("CLOSED_PARENTHESES", r"\)"),
        ("DOUBLE", r"-?\d+\.\d+[Dd]"),
        ("FLOAT", r"-?\d+\.\d+"),
        ("INTEGER", r"-?\d+"),
        ("BOOLEAN", r"true|false"),
        ("IDENT", r"[a-zA-Z0-9!$%&*+-./:<=>?@^_~]+"),
        ("STRING", r'"[^"\\]*(?:\\.[^"\\]*)*"'),
        ("SKIP", r"[ \t\n]+"),
        ("UNDEFINED", r"."),
    ]

    regex = "|".join(f"(?P<{name}>{pattern})" for name, pattern in token_spec)

    for mo in re.finditer(regex, source):
        kind = mo.lastgroup
        value = mo.group()

        if not kind or kind == "SKIP":
            continue

        yield LexerToken(LexerTokenType[kind], value)

    yield LexerToken(LexerTokenType.EOF, "")
