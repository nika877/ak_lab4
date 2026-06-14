"""CLI-обёртка: компилирует файл с исходным кодом на Nika и запускает его
через программный интерпретатор (`lang.runtime.interpret`).

Использование:
    python interpreter.py <path-to-source.lisp> [<path-to-input.txt>]
"""

from __future__ import annotations

import sys

from lang.exceptions import PipelineError
from lang.formatter import print_bytecode
from lang.pipeline import compile_source
from lang.runtime import interpret


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        print(
            "Использование: python interpreter.py <source.lisp> [<input.txt>]",
            file=sys.stderr,
        )
        return 2

    with open(argv[1], encoding="utf-8") as f:
        source = f.read()

    input_data: list[int] = []
    if len(argv) == 3:
        with open(argv[2], encoding="utf-8") as f:
            input_data = [ord(c) for c in f.read()]

    try:
        compiled = compile_source(source)
        print_bytecode(compiled.bytecode, compiled.meta)

        acc, output, _ = interpret(compiled.bytecode, compiled.entry_point, input_data=input_data)
    except PipelineError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if output:
        sys.stdout.write(output)
        if not output.endswith("\n"):
            sys.stdout.write("\n")
    print(f"ACC AFTER HALT: {acc}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
