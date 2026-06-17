"""Пайплайн компиляции: исходный текст → байткод.

Здесь собраны все этапы трансляции в правильном порядке:

1. tokenize         — лексер разбивает текст на токены
2. parse            — парсер строит дерево S-выражений и назначает имена
3. infer (1)        — первый проход вывода типов (до CPS, для встроенных функций)
4. cps_transform    — перевод в CPS (Continuation-Passing Style)
5. assign_qualnames — повторное назначение имён после CPS
6. infer (2)        — второй проход вывода типов (после CPS)
7. Compiler.compile — генерация байткода и раскладка памяти

Этот модуль — «оркестратор»: он не содержит логики самих стадий, а только
вызывает их в нужном порядке и передаёт результаты между ними. Каждая стадия
реализована в своём модуле; здесь видна общая структура процесса.
"""

from __future__ import annotations

# StringIO — «буфер в памяти», эмулирующий файл. Используется в run_source(),
# чтобы перехватить вывод программы вместо печати в stdout.
from io import StringIO

# CompilationResult — итоговая структура: байткод + entry_point + метаданные памяти.
# Compiler — класс, который собирает байткод из типизированного CPS-дерева.
from lang.compiler import CompilationResult, Compiler
# infer — алгоритм Хиндли-Милнера: расставляет типы каждому узлу.
# Вызывается дважды (см. ниже, в коде функции).
from lang.compiler.inferrer import infer
# tokenize — лексер: текст → последовательность токенов (числа, скобки, идентификаторы).
from lang.lexer import tokenize
# parse — парсер: токены → дерево S-выражений с разрешёнными именами.
# ParserResult — структура результата парсера (хранилище + словари путей).
# assign_qualnames — назначает квалифицированные имена (qualname) узлам дерева.
# cps_transform — переписывает дерево в CPS-форму (см. lang/parser/cps.py).
from lang.parser import ParserResult, assign_qualnames, cps_transform, parse
# interpret — программный исполнитель байткода (быстрая проверка корректности).
from lang.runtime import interpret


def compile_source(source: str) -> CompilationResult:
    """Скомпилировать строку с исходным кодом в байткод.

    Главная функция трансляции. Принимает текст программы, возвращает
    готовый бинарный образ + метаданные. Все стадии вызываются здесь
    в строго определённом порядке.
    """
    # Стадии 1+2: лексер выдаёт поток токенов, парсер строит из них AST.
    # parse() уже включает в себя assign_qualnames (см. lang/parser/__init__.py).
    parsed = parse(tokenize(source))

    # Стадия 3: первый проход вывода типов.
    # Зачем use_semantic_types=True: до CPS встроенные функции (например +) имеют
    # «пользовательские» сигнатуры без явного аргумента-продолжения. CPS-трансформер
    # использует эти типы, чтобы понять, какие вызовы можно сделать атомарными
    # (вставить инструкцию инлайн вместо отдельного вызова).
    inferred_semantic = infer(parsed, use_semantic_types=True)

    # Стадия 4: CPS-трансформация — переписывает дерево так, что у каждой
    # функции появляется явный аргумент-продолжение k. Это нужно потому что
    # у нашей аккумуляторной ISA нет ни стека, ни команд call/ret —
    # «возвраты» из функций реализуются через JMP к адресу продолжения.
    cps_storage = cps_transform(inferred_semantic.storage)
    # Стадия 5: после CPS все узлы поменяли свои пути в дереве и появилось
    # много новых лямбд-продолжений. Поэтому нужно заново раздать им qualname.
    cps_qn = assign_qualnames(cps_storage)
    # Собираем ParserResult из результатов qualname-assign — это контейнер,
    # который ждёт следующая стадия (infer).
    cps_result = ParserResult(
        cps_qn.storage,
        cps_qn.all_tokens,
        cps_qn.mutable_paths,    # переменные, мутируемые через setq
        cps_qn.autoboxed_paths,  # переменные в куче (мутируемые + захваченные лямбдой)
    )

    # Стадия 6: второй проход вывода типов — уже на CPS-дереве.
    # use_semantic_types=False: теперь встроенные функции используются в своей
    # CPS-форме (с дополнительным параметром k), и инферрер должен это учитывать.
    inferred = infer(cps_result, use_semantic_types=False)

    # Стадия 7: компилятор обходит типизированное CPS-дерево и генерирует
    # реальный байткод. Возвращает CompilationResult с готовым bytes.
    return Compiler.compile(inferred)


def run_source(
    source: str,
    input_data: list[int] | None = None,
    output_stream: StringIO | None = None,
) -> tuple[int, str, list[str]]:
    """Скомпилировать и сразу выполнить (удобно для тестов).

    Аргументы:
        source       — исходный код Lisp-программы
        input_data   — список кодов символов для (input) (моделирует PORT_IN)
        output_stream — куда писать вывод программы (по умолчанию во внутренний буфер)

    Возвращает: (acc после HALT, строка вывода, список такт-логов).
    Эта функция используется в тестах (tests/test_golden.py).
    """
    compiled = compile_source(source)
    return interpret(
        compiled.bytecode,
        compiled.entry_point,
        input_data=input_data,
        output_stream=output_stream,
    )