"""Golden-тесты компилятора и обоих рантаймов (программного + аппаратного).

Кейсы хранятся в `tests/cases/**/<name>.lisp` рядом с тремя артефактами:

  <name>.lisp     -- исходный код
  <name>.json     -- ожидания: {"acc", "output"?, "input"?, ...}
  <name>.bin.txt  -- эталонный дамп бинарного кода (адрес - hex - mnemonic)
  <name>.log.txt  -- эталонный фрагмент журнала работы машины (см. _trim_log)

Формат `<name>.json`:

    {
      "acc": <int>,            // ожидаемое значение acc после HALT
      "output": "<str>",       // ожидаемый текст в PORT_OUT (опц.)
      "output_startswith": "", // альтернатива для приближённых сравнений (опц.)
      "input": [<int>, ...],   // ввод через trap-механизм (опц.)
      "machine_parity": true,  // прогнать ещё и через аппаратную модель (опц., default true)
      "skip": "<reason>"       // если задано -- кейс будет пропущен с причиной
    }

Регенерация эталонов: установить переменную окружения `REGEN=1` и запустить
тесты -- *.bin.txt и *.log.txt будут перезаписаны (acc/output из .json -- нет,
их пользователь правит руками).
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from lang.isa import WORD_LEN, to_hex
from lang.machine import SimulationResult, simulation
from lang.pipeline import compile_source
from lang.runtime import interpret

CASES_ROOT = Path(__file__).parent / "cases"

REGEN = bool(os.environ.get("REGEN"))


def _load_case(lisp_path: Path) -> tuple[str, dict]:
    source = lisp_path.read_text(encoding="utf-8")
    expected = json.loads(lisp_path.with_suffix(".json").read_text(encoding="utf-8"))
    return source, expected


def _all_cases() -> list[Path]:
    return sorted(CASES_ROOT.rglob("*.lisp"))


def _trim_log(log: list[str], head: int = 30, tail: int = 10) -> str:
    """Адаптировать журнал под golden-формат: первые head + последние tail строк +
    все строки с PORT_OUT / IRET / HALT (как репрезентативные опорные точки).

    Если журнал короче head+tail, отдаётся целиком."""
    if len(log) <= head + tail:
        return "\n".join(log)

    keep_idx: set[int] = set(range(head)) | set(range(len(log) - tail, len(log)))
    for i, line in enumerate(log):
        if "PORT_OUT" in line or "IRET" in line or "HALT" in line or "INT" in line:
            keep_idx.add(i)

    lines: list[str] = []
    prev = -2
    for i in sorted(keep_idx):
        if i != prev + 1 and lines:
            lines.append(f"... ({i - prev - 1} lines elided) ...")
        lines.append(log[i])
        prev = i
    return "\n".join(lines)


def _check_or_write_artifact(
    path: Path, actual: str, test_case: unittest.TestCase, label: str
) -> None:
    if REGEN or not path.exists():
        path.write_text(actual + "\n", encoding="utf-8")
        return
    expected = path.read_text(encoding="utf-8").rstrip("\n")
    if expected != actual:
        # Сообщение должно подсказать, как обновить эталон.
        test_case.fail(
            f"{label} mismatch for {path.name}. "
            f"To regenerate: set REGEN=1 and rerun.\n"
            f"--- expected (first 20 lines) ---\n"
            + "\n".join(expected.splitlines()[:20])
            + "\n--- actual (first 20 lines) ---\n"
            + "\n".join(actual.splitlines()[:20])
        )


class GoldenCases(unittest.TestCase):
    """Параметризованные тесты по каталогу `cases/`."""

    @staticmethod
    def _make_test(lisp_path: Path):
        rel = lisp_path.relative_to(CASES_ROOT).with_suffix("")
        bin_path = lisp_path.with_suffix(".bin.txt")
        log_path = lisp_path.with_suffix(".log.txt")

        def run(self):
            source, expected = _load_case(lisp_path)
            if reason := expected.get("skip"):
                self.skipTest(reason)

            input_data = expected.get("input")
            compiled = compile_source(source)
            acc, output, _ = interpret(
                compiled.bytecode, compiled.entry_point, input_data=input_data
            )
            self.assertEqual(acc, expected["acc"], f"acc mismatch on {rel}")

            if "output" in expected:
                self.assertEqual(output, expected["output"], f"output mismatch on {rel}")
            if "output_startswith" in expected:
                self.assertTrue(
                    output.startswith(expected["output_startswith"]),
                    f"output prefix mismatch on {rel}: {output!r}",
                )

            code_start = len(compiled.meta.memory.slots) * WORD_LEN

            # bin.txt: полный мнемонический дамп бинарного кода.
            bin_dump = to_hex(compiled.bytecode, code_start)
            _check_or_write_artifact(bin_path, bin_dump, self, "binary dump")

            machine_seq: SimulationResult | None = None
            if expected.get("machine_parity", True):
                machine_seq = simulation(
                    compiled.bytecode,
                    compiled.entry_point,
                    code_start,
                    input_data or [],
                )
                self.assertEqual(
                    machine_seq.acc,
                    expected["acc"],
                    f"machine (seq) disagrees on {rel}",
                )
                if "output" in expected:
                    self.assertEqual(
                        machine_seq.output,
                        expected["output"],
                        f"machine (seq) output diverges on {rel}",
                    )

            # log.txt: репрезентативный фрагмент журнала seq-модели.
            if machine_seq is None:
                # Если parity-чекинг выключен, всё равно получаем лог для эталона.
                machine_seq = simulation(
                    compiled.bytecode,
                    compiled.entry_point,
                    code_start,
                    input_data or [],
                )
            log_dump = _trim_log(machine_seq.log)
            _check_or_write_artifact(log_path, log_dump, self, "machine log")

        run.__doc__ = str(rel)
        return run


def _register_cases() -> None:
    """Сгенерировать по test_-методу на каждый файл в `cases/`."""
    for lisp_path in _all_cases():
        rel = lisp_path.relative_to(CASES_ROOT).with_suffix("")
        name = "test_" + str(rel).replace("\\", "__").replace("/", "__").replace("-", "_")
        setattr(GoldenCases, name, GoldenCases._make_test(lisp_path))


_register_cases()


if __name__ == "__main__":
    unittest.main()
