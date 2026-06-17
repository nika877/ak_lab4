"""Интерпретатор Lisp-программы «на лету».

В отличие от translator.py, здесь программа не сохраняется в файл — она
компилируется в памяти и сразу выполняется программным интерпретатором
(упрощённая модель процессора, без пошаговой симуляции железа).

Использование:
    python interpreter.py <source.lisp> [<input.txt>]

Нужен для быстрой проверки, что компилятор выдал корректный байткод:
если интерпретатор посчитал результат правильно, значит проблемы в коде нет.
Это полезно при отладке, потому что аппаратная модель (lang/machine.py)
работает медленнее и её логи труднее читать.
"""

from __future__ import annotations

# sys — для argv (аргументы CLI), stderr (поток ошибок) и stdout (вывод).
import sys

# PipelineError — общая ошибка любой стадии компиляции
# (наследники: ParserError, InferrerError, CompilerError).
from lang.exceptions import PipelineError
# print_bytecode — печать байткода в человеко-читаемом виде (отладочный дамп).
from lang.formatter import print_bytecode
# compile_source — оркестратор всех стадий пайплайна (лексер → ... → байткод).
from lang.pipeline import compile_source
# interpret — программный исполнитель команд: эмулирует ALU/acc/память,
# но без потактовой логики (мгновенно «прогоняет» программу до HALT).
from lang.runtime import interpret


def main(argv: list[str]) -> int:
    """Скомпилировать исходник, выполнить и вывести результат в ACC.

    Возвращает код выхода процесса: 0 — успех, 1 — ошибка компиляции,
    2 — неправильное использование (не те аргументы).
    """
    # Ожидаем 1 или 2 полезных аргумента (плюс argv[0] — имя скрипта).
    # Второй аргумент необязательный — это файл с входными данными для (input).
    if len(argv) not in (2, 3):
        print(
            "Использование: python interpreter.py <source.lisp> [<input.txt>]",
            file=sys.stderr,
        )
        return 2

    # Читаем весь исходник в строку. Для учебных программ это безопасно
    # — файлы небольшие.
    with open(argv[1], encoding="utf-8") as f:
        source = f.read()

    # Ввод для встроенной функции (input): каждый символ файла превращается
    # в код символа (целое число). Программа потом будет вычитывать их по одному.
    # Это эмуляция работы порта PORT_IN из карты памяти ВМ.
    input_data: list[int] = []
    if len(argv) == 3:
        with open(argv[2], encoding="utf-8") as f:
            # ord(c) — стандартная Python-функция: символ → его Unicode-код.
            # Например ord("A") = 65, ord("я") = 1103.
            input_data = [ord(c) for c in f.read()]

    try:
        # Компиляция: текст → байткод + метаданные о размещении в памяти.
        compiled = compile_source(source)
        # Отладочный дамп: показать, какие команды получились.
        # При защите можно показать вывод и пройтись по командам.
        print_bytecode(compiled.bytecode, compiled.meta)

        # Запуск программного интерпретатора. Возвращает кортеж:
        #   acc — значение аккумулятора после HALT
        #   output — строка вывода программы (всё, что напечатал print)
        #   _ — служебная информация (отбрасываем, т.к. не нужна здесь)
        acc, output, _ = interpret(
            compiled.bytecode,
            compiled.entry_point,
            input_data=input_data,
        )
    except PipelineError as exc:
        # Ловит ошибки и компиляции, и работы интерпретатора.
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # Выводим всё, что напечатала программа через (print ...).
    if output:
        sys.stdout.write(output)
        # Добавим перевод строки, если программа сама его не поставила —
        # иначе строка результата ниже прилипнет к выводу программы.
        if not output.endswith("\n"):
            sys.stdout.write("\n")
    # Финальное значение acc — типичный «результат программы» в твоей модели.
    # У задачи Эйлера №1, например, это будет сумма кратных 3 и 5.
    print(f"ACC AFTER HALT: {acc}")
    return 0


# Защита «запускать main только при прямом запуске файла».
# При импорте этого модуля main() не сработает.
if __name__ == "__main__":
    sys.exit(main(sys.argv))