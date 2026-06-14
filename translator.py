"""Транслятор языка.

Использование:
    python translator.py <source.lisp> <output.bin>

Результат:
    <output.bin>       — бинарный образ (память данных + байткод).
    <output.bin>.entry — 8 байт: entry_point (4 байта) + code_start (4 байта).

Дополнительно на stdout выводится hex дамп для отладки.
"""

from __future__ import annotations

import struct
import sys

from lang.compiler.bytecode import WordMemory
from lang.exceptions import PipelineError
from lang.isa import WORD_LEN, to_hex
from lang.pipeline import compile_source


def translate(source_path: str, out_path: str) -> int:
    with open(source_path, encoding="utf-8") as f:
        source = f.read()

    try:
        compiled = compile_source(source)
    except PipelineError as exc:
        print(f"ошибка компиляции: {exc}", file=sys.stderr)
        return 1

    with open(out_path, "wb") as f:
        f.write(compiled.bytecode)

    code_start = len(compiled.meta.memory.slots) * WORD_LEN
    entry_point = compiled.entry_point
    with open(out_path + ".entry", "wb") as f:
        f.write(struct.pack("<i", entry_point))
        f.write(struct.pack("<i", code_start))

    bc = WordMemory(compiled.bytecode, WORD_LEN)
    _ = bc
    dump = to_hex(compiled.bytecode, code_start)
    print(dump)

    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(
            "Использование: python translator.py <source.lisp> <output.bin>",
            file=sys.stderr,
        )
        return 2
    return translate(argv[1], argv[2])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
