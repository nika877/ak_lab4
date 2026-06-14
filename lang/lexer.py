import re
from dataclasses import dataclass
from enum import Enum, auto


class LexerTokenType(Enum):
    OPEN_PARENTHESES = auto()
    CLOSED_PARENTHESES = auto()
    FLOAT = auto()
    DOUBLE = auto()
    INTEGER = auto()
    BOOLEAN = auto()
    IDENT = auto()
    STRING = auto()
    UNDEFINED = auto()
    SKIP = auto()
    EOF = auto()


@dataclass(frozen=True, slots=True)
class LexerToken:
    ty: LexerTokenType
    source: str


def tokenize(source: str):
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
