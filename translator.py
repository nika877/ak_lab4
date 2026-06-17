"""Транслятор Lisp-программы в бинарный образ для виртуальной машины.

Это главная точка входа для компиляции: читает .lisp-файл, прогоняет через
весь пайплайн (лексер → парсер → CPS → типы → байткод) и сохраняет результат.

Использование:
    python translator.py <source.lisp> <output.bin>

Результат:
    <output.bin>       — бинарный образ (память данных + байткод).
    <output.bin>.entry — 8 байт: entry_point (4 байта) + code_start (4 байта).

Дополнительно на stdout выводится hex-дамп команд для отладки.
"""

from __future__ import annotations

# struct — стандартный модуль для упаковки/распаковки чисел в байты
# (нужен, чтобы записать entry_point и code_start в little-endian формате).
import struct

# sys — доступ к argv (аргументы командной строки) и stderr (поток ошибок).
import sys

# WordMemory — обёртка над bytes, которая трактует их как массив машинных слов
# (см. lang/compiler/bytecode.py). Здесь используется только для отладки.
from lang.compiler.bytecode import WordMemory

# PipelineError — общий тип исключений всего пайплайна
# (наследники: ParserError, InferrerError, CompilerError).
from lang.exceptions import PipelineError

# WORD_LEN — длина одного машинного слова в байтах (4, потому что архитектура 32-битная).
# to_hex — функция, формирующая человеко-читаемый дамп памяти и кода.
from lang.isa import WORD_LEN, to_hex

# compile_source — оркестратор всех 8 стадий компиляции (см. lang/pipeline.py).
from lang.pipeline import compile_source


def translate(source_path: str, out_path: str) -> int:
    """Скомпилировать исходник и записать бинарный образ на диск.

    Возвращает код выхода процесса: 0 — успех, 1 — ошибка компиляции.
    """
    # Читаем весь исходник в память как текст в кодировке UTF-8.
    # Файлы Lisp небольшие, держать всё в строке — допустимо.
    with open(source_path, encoding="utf-8") as f:
        source = f.read()

    try:
        # Полный пайплайн компиляции: текст → байткод + метаданные.
        # На выходе compiled.bytecode уже представляет готовый образ памяти:
        # сначала слоты данных, потом сам код (см. Compiler.compile).
        compiled = compile_source(source)
    except PipelineError as exc:
        # Любая ошибка на любой стадии пайплайна (парсер, типы, компилятор)
        # доходит сюда. Печатаем сообщение и возвращаем ненулевой код выхода.
        print(f"ошибка компиляции: {exc}", file=sys.stderr)
        return 1

    # Сохраняем бинарный образ: одна непрерывная последовательность байт,
    # которую виртуальная машина загрузит в свою память «как есть».
    with open(out_path, "wb") as f:
        f.write(compiled.bytecode)

    # code_start — байтовый адрес первой инструкции в образе.
    # Все ячейки данных лежат до code_start, поэтому он = (число слотов) * 4.
    code_start = len(compiled.meta.memory.slots) * WORD_LEN
    # entry_point — адрес инструкции, с которой нужно начинать выполнение.
    # Обычно указывает на main, иногда — на пролог инициализации.
    entry_point = compiled.entry_point
    # Записываем оба числа в отдельный файл .entry в little-endian формате.
    # ВМ читает его при загрузке, чтобы знать, куда прыгать стартом.
    with open(out_path + ".entry", "wb") as f:
        f.write(struct.pack("<i", entry_point))
        f.write(struct.pack("<i", code_start))

    # Создаём WordMemory чисто для контроля корректности (можно не использовать).
    # Переменная _ — стандартное соглашение «значение не нужно».
    bc = WordMemory(compiled.bytecode, WORD_LEN)
    _ = bc
    # Печатаем дамп: адрес + опкод + мнемоника + аргумент.
    # Удобно при ручной отладке — видно, что именно сгенерировал компилятор.
    dump = to_hex(compiled.bytecode, code_start)
    print(dump)

    return 0


def main(argv: list[str]) -> int:
    """Разбор аргументов командной строки.

    Ожидает ровно два аргумента: входной .lisp и путь выходного бинарника.
    """
    # argv[0] — имя самого скрипта, поэтому полезных аргументов должно быть 2.
    if len(argv) != 3:
        print(
            "Использование: python translator.py <source.lisp> <output.bin>",
            file=sys.stderr,
        )
        # Код 2 — стандартное соглашение об ошибке использования (misuse).
        return 2
    return translate(argv[1], argv[2])


# Защита from "если файл импортирован, а не запущен напрямую".
# Без неё main() запускалось бы при любом импорте.
if __name__ == "__main__":
    # sys.exit передаёт код возврата в ОС.
    sys.exit(main(sys.argv))
