"""Тесты, специфичные для аппаратной модели (`lang/machine.py`).

Параллельность результатов с программным интерпретатором уже покрыта в
`tests/test_golden.py` (см. `machine_parity` в каждом JSON-кейсе).
Здесь остаются только проверки, специфичные именно для модели:

- метрики симуляции (тики, инструкции);
- бинарный ISA декодируется обратно (`iter_program`, `to_hex`).
"""

import unittest

from lang.isa import BC, WORD_LEN, iter_program, to_hex
from lang.machine import simulation
from lang.pipeline import compile_source

EULER1 = (
    "(defun triangular (m) (/ (* m (+ m 1)) 2))\n"
    "(defun sum-k (n k) (* k (triangular (/ (- n 1) k))))\n"
    "(- (+ (sum-k 1000 3) (sum-k 1000 5)) (sum-k 1000 15))\n"
)


def _run(source: str):
    compiled = compile_source(source)
    code_start = len(compiled.meta.memory.slots) * WORD_LEN
    return simulation(
        compiled.bytecode,
        compiled.entry_point,
        code_start,
        [],

    )

class TestISADecoder(unittest.TestCase):
    """Бинарный образ декодируется обратно `iter_program` / `to_hex`."""

    def test_iter_program_recovers_opcodes(self):
        compiled = compile_source("(defun id (x) x) (id 42)")
        code_start = len(compiled.meta.memory.slots) * WORD_LEN
        ops = [op for _, op, _, _ in iter_program(compiled.bytecode, code_start)]
        self.assertGreater(len(ops), 0)
        for expected in (BC.HALT, BC.STORE_MEM, BC.LOAD_MEM, BC.JMP):
            self.assertIn(expected, ops)

    def test_to_hex_format(self):
        compiled = compile_source("(+ 2 3)")
        code_start = len(compiled.meta.memory.slots) * WORD_LEN
        dump = to_hex(compiled.bytecode, code_start)
        self.assertIn("HALT", dump)
        for line in dump.splitlines():
            self.assertIn(" - ", line)


if __name__ == "__main__":
    unittest.main()
