"""Встроенные операции со строками: concat, sort-string!, сравнение."""

import lang.compiler as compiler
from lang.compiler.bytecode import BC
from lang.lang_type import (
    FunctionLanguageType,
    PrimitiveLanguageType,
)
from lang.parser.qualname import (
    BuiltinSymbol,
    LambdaEmitter,
    TreePathEntry,
)


def builtin_to_integer_unchecked_string():
    """Parse integer from string: "123" -> 123, "-45" -> -45"""

    def emit_to_int_bytecode(unit, slots, k, *args):
        # 1. Инициализация переменных
        unit.bytecode.extend(
            [
                BC.LOAD_MEM,
                args[0],
                BC.STORE_MEM,
                slots[0],  # STR_PTR
                BC.LOAD_IND_MEM,
                slots[0],
                BC.STORE_MEM,
                slots[1],  # LEN = *STR_PTR
                BC.LOAD_IMM,
                0,
                BC.STORE_MEM,
                slots[2],  # RES = 0
                BC.STORE_MEM,
                slots[3],  # IS_NEG = 0
                # PTR = STR_PTR + WORD_LEN (пропускаем слово длины)
                BC.LOAD_MEM,
                slots[0],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[4],
                # END_PTR = PTR + LEN * WORD_LEN
                BC.LOAD_MEM,
                slots[1],
                BC.MUL_IMM,
                compiler.Memory.WORD_LEN,
                BC.ADD_MEM,
                slots[4],
                BC.STORE_MEM,
                slots[5],
            ]
        )

        # Проверка на пустую строку (LEN == 0 -> PTR == END_PTR)
        unit.bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[4],
                BC.EQ_MEM,
                slots[5],
                BC.JMP_T,
                0,  # Заглушка: если пустая, сразу идем к выходу
            ]
        )
        jmp_empty_idx = len(unit.bytecode) - 1

        # 2. Проверка знака '-'
        unit.bytecode.extend(
            [
                BC.LOAD_IND_MEM,
                slots[4],
                BC.NE_IMM,
                45,  # 45 это ASCII-код '-'
                BC.JMP_T,
                0,  # Заглушка: если не '-', прыгаем к основному циклу
            ]
        )
        jmp_to_loop_idx = len(unit.bytecode) - 1

        # Если символ '-', помечаем флаг и сдвигаем указатель
        unit.bytecode.extend(
            [
                BC.LOAD_IMM,
                1,
                BC.STORE_MEM,
                slots[3],  # IS_NEG = 1
                BC.LOAD_MEM,
                slots[4],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[4],  # PTR++
            ]
        )

        # 3. Основной цикл
        loop_start = len(unit.bytecode) * compiler.Memory.WORD_LEN
        # Патчим прыжок к циклу (для позитивных чисел он прыгнет сюда)
        unit.bytecode[jmp_to_loop_idx] = loop_start

        unit.bytecode.extend(
            [
                # Условие выхода из цикла: PTR == END_PTR
                BC.LOAD_MEM,
                slots[4],
                BC.EQ_MEM,
                slots[5],
                BC.JMP_T,
                0,  # Заглушка: выход из цикла
            ]
        )
        jmp_exit_idx = len(unit.bytecode) - 1

        unit.bytecode.extend(
            [
                # RES = RES * 10
                BC.LOAD_MEM,
                slots[2],
                BC.MUL_IMM,
                10,
                BC.STORE_MEM,
                slots[2],
                # ACC = char - 48
                BC.LOAD_IND_MEM,
                slots[4],
                BC.SUB_IMM,
                48,
                # RES = RES + ACC
                BC.ADD_MEM,
                slots[2],
                BC.STORE_MEM,
                slots[2],
                # PTR += WORD_LEN
                BC.LOAD_MEM,
                slots[4],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[4],
                # Повтор
                BC.JMP,
                loop_start,
            ]
        )

        exit_offset = len(unit.bytecode) * compiler.Memory.WORD_LEN
        unit.bytecode[jmp_exit_idx] = exit_offset  # Патчим выход из цикла
        unit.bytecode[jmp_empty_idx] = exit_offset  # Патчим выход из-за пустой строки

        # 4. Применение знака
        unit.bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[3],
                BC.EQ_IMM,
                0,
                BC.JMP_T,
                0,  # Заглушка: если IS_NEG == 0, пропускаем инверсию
            ]
        )
        jmp_skip_neg_idx = len(unit.bytecode) - 1

        unit.bytecode.extend(
            [
                BC.LOAD_IMM,
                0,
                BC.SUB_MEM,
                slots[2],
                BC.STORE_MEM,
                slots[2],  # RES = 0 - RES (инвертируем)
            ]
        )

        unit.bytecode[jmp_skip_neg_idx] = len(unit.bytecode) * compiler.Memory.WORD_LEN

        # 5. CPS-вызов продолжения
        compiler.Compiler.emit_write_args_inplace(unit, [[BC.LOAD_MEM, slots[2]]])
        compiler.Compiler.emit_load_k(unit, k)
        compiler.Compiler.emit_apply_k(unit)

    return BuiltinSymbol(
        source="to-integer-unchecked",
        path=TreePathEntry.for_builtin("to-integer-unchecked<string>").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.STRING,
                FunctionLanguageType([PrimitiveLanguageType.INTEGER], typevar_emitter()),
            ],
            PrimitiveLanguageType.VOID,
        ),
        emit_inplace=None,
        emit_lambda=LambdaEmitter(
            slots=["STR_PTR", "LEN", "RES", "IS_NEG", "PTR", "END_PTR"],
            bytecode_emitter=emit_to_int_bytecode,
        ),
    )


def builtin_concat_string():
    def emit_concat_string_bytecode(unit, slots, k, *args):
        bytecode = unit.bytecode

        # 1. Загрузка указателей и чтение длин строк (Pascal-формат: [длина, char, char...])
        bytecode.extend(
            [
                BC.LOAD_MEM,
                args[0],
                BC.STORE_MEM,
                slots[0],  # STR1 = args[0]
                BC.LOAD_MEM,
                args[1],
                BC.STORE_MEM,
                slots[1],  # STR2 = args[1]
                BC.LOAD_IND_MEM,
                slots[0],
                BC.STORE_MEM,
                slots[2],  # LEN1 = *STR1
                BC.LOAD_IND_MEM,
                slots[1],
                BC.STORE_MEM,
                slots[3],  # LEN2 = *STR2
            ]
        )

        # 2. Вычисление новой длины: NEW_LEN = LEN1 + LEN2
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[2],
                BC.ADD_MEM,
                slots[3],
                BC.STORE_MEM,
                slots[4],
            ]
        )

        # 3. Выделение памяти в HEAP (NEW_STR = текущий HEAP)
        bytecode.extend(
            [
                BC.LOAD_MEM,
                compiler.Memory.HEAP,
                BC.STORE_MEM,
                slots[5],  # NEW_STR = HEAP
                # Вычисляем размер блока: (NEW_LEN + 1) * WORD_LEN
                BC.LOAD_MEM,
                slots[4],
                BC.ADD_IMM,
                1,
                BC.MUL_IMM,
                compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[6],
                # Сдвигаем HEAP: HEAP = NEW_STR + размер_блока
                BC.LOAD_MEM,
                slots[5],
                BC.ADD_MEM,
                slots[6],
                BC.STORE_MEM,
                compiler.Memory.HEAP,
            ]
        )

        # 4. Запись длины в заголовок новой строки
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[4],
                BC.STORE_IND_MEM,
                slots[5],
            ]
        )

        # 5. Инициализация цикла копирования первой строки
        bytecode.extend(
            [
                BC.LOAD_IMM,
                0,
                BC.STORE_MEM,
                slots[6],  # I = 0 (переиспользуем слот 6)
                BC.LOAD_MEM,
                slots[0],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[7],  # SRC = STR1 + WORD_LEN
                BC.LOAD_MEM,
                slots[5],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[8],  # DEST = NEW_STR + WORD_LEN
            ]
        )

        # Цикл 1: Копирование символов из STR1
        loop1_start = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[6],
                BC.EQ_MEM,
                slots[2],
                BC.JMP_T,
                -1,  # if I == LEN1 -> выход
            ]
        )
        jmp1_exit_idx = len(bytecode) - 1

        bytecode.extend(
            [
                BC.LOAD_IND_MEM,
                slots[7],
                BC.STORE_IND_MEM,
                slots[8],  # *DEST = *SRC
                BC.LOAD_MEM,
                slots[7],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[7],  # SRC++
                BC.LOAD_MEM,
                slots[8],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[8],  # DEST++
                BC.LOAD_MEM,
                slots[6],
                BC.ADD_IMM,
                1,
                BC.STORE_MEM,
                slots[6],  # I++
                BC.JMP,
                loop1_start,
            ]
        )
        bytecode[jmp1_exit_idx] = len(bytecode) * compiler.Memory.WORD_LEN

        # 6. Подготовка к копированию второй строки
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[1],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[7],  # SRC = STR2 + WORD_LEN
                # I уже равен LEN1, продолжим считать до NEW_LEN
            ]
        )

        # Цикл 2: Копирование символов из STR2
        loop2_start = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[6],
                BC.EQ_MEM,
                slots[4],
                BC.JMP_T,
                -1,  # if I == NEW_LEN -> выход
            ]
        )
        jmp2_exit_idx = len(bytecode) - 1

        bytecode.extend(
            [
                BC.LOAD_IND_MEM,
                slots[7],
                BC.STORE_IND_MEM,
                slots[8],  # *DEST = *SRC
                BC.LOAD_MEM,
                slots[7],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[7],  # SRC++
                BC.LOAD_MEM,
                slots[8],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[8],  # DEST++
                BC.LOAD_MEM,
                slots[6],
                BC.ADD_IMM,
                1,
                BC.STORE_MEM,
                slots[6],  # I++
                BC.JMP,
                loop2_start,
            ]
        )
        bytecode[jmp2_exit_idx] = len(bytecode) * compiler.Memory.WORD_LEN

        # 7. CPS-вызов продолжения с указателем на сконкатенированную строку
        compiler.Compiler.emit_write_args_inplace(unit, [[BC.LOAD_MEM, slots[5]]])
        compiler.Compiler.emit_load_k(unit, k)
        compiler.Compiler.emit_apply_k(unit)

    return BuiltinSymbol(
        source="concat",
        path=TreePathEntry.for_builtin("concat<string>").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.STRING,
                PrimitiveLanguageType.STRING,
                FunctionLanguageType([PrimitiveLanguageType.STRING], typevar_emitter()),
            ],
            PrimitiveLanguageType.VOID,
        ),
        emit_inplace=None,
        emit_lambda=LambdaEmitter(
            slots=[
                "STR1",
                "STR2",
                "LEN1",
                "LEN2",
                "NEW_LEN",
                "NEW_STR",
                "I",
                "SRC",
                "DEST",
            ],
            bytecode_emitter=emit_concat_string_bytecode,
        ),
    )


def builtin_add_string():
    """String addition via concatenation: "hello" + " world" -> "hello world".

    Clone of builtin_concat_string() with source="+" and path +<string>.
    """

    def emit_add_string_bytecode(unit, slots, k, *args):
        bytecode = unit.bytecode

        bytecode.extend(
            [
                BC.LOAD_MEM,
                args[0],
                BC.STORE_MEM,
                slots[0],
                BC.LOAD_MEM,
                args[1],
                BC.STORE_MEM,
                slots[1],
                BC.LOAD_IND_MEM,
                slots[0],
                BC.STORE_MEM,
                slots[2],
                BC.LOAD_IND_MEM,
                slots[1],
                BC.STORE_MEM,
                slots[3],
            ]
        )

        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[2],
                BC.ADD_MEM,
                slots[3],
                BC.STORE_MEM,
                slots[4],
            ]
        )

        bytecode.extend(
            [
                BC.LOAD_MEM,
                compiler.Memory.HEAP,
                BC.STORE_MEM,
                slots[5],
                BC.LOAD_MEM,
                slots[4],
                BC.ADD_IMM,
                1,
                BC.MUL_IMM,
                compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[6],
                BC.LOAD_MEM,
                slots[5],
                BC.ADD_MEM,
                slots[6],
                BC.STORE_MEM,
                compiler.Memory.HEAP,
            ]
        )

        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[4],
                BC.STORE_IND_MEM,
                slots[5],
            ]
        )

        bytecode.extend(
            [
                BC.LOAD_IMM,
                0,
                BC.STORE_MEM,
                slots[6],
                BC.LOAD_MEM,
                slots[0],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[7],
                BC.LOAD_MEM,
                slots[5],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[8],
            ]
        )

        loop1_start = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[6],
                BC.EQ_MEM,
                slots[2],
                BC.JMP_T,
                -1,
            ]
        )
        jmp1_exit_idx = len(bytecode) - 1

        bytecode.extend(
            [
                BC.LOAD_IND_MEM,
                slots[7],
                BC.STORE_IND_MEM,
                slots[8],
                BC.LOAD_MEM,
                slots[7],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[7],
                BC.LOAD_MEM,
                slots[8],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[8],
                BC.LOAD_MEM,
                slots[6],
                BC.ADD_IMM,
                1,
                BC.STORE_MEM,
                slots[6],
                BC.JMP,
                loop1_start,
            ]
        )
        bytecode[jmp1_exit_idx] = len(bytecode) * compiler.Memory.WORD_LEN

        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[1],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[7],
            ]
        )

        loop2_start = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[6],
                BC.EQ_MEM,
                slots[4],
                BC.JMP_T,
                -1,
            ]
        )
        jmp2_exit_idx = len(bytecode) - 1

        bytecode.extend(
            [
                BC.LOAD_IND_MEM,
                slots[7],
                BC.STORE_IND_MEM,
                slots[8],
                BC.LOAD_MEM,
                slots[7],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[7],
                BC.LOAD_MEM,
                slots[8],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[8],
                BC.LOAD_MEM,
                slots[6],
                BC.ADD_IMM,
                1,
                BC.STORE_MEM,
                slots[6],
                BC.JMP,
                loop2_start,
            ]
        )
        bytecode[jmp2_exit_idx] = len(bytecode) * compiler.Memory.WORD_LEN

        compiler.Compiler.emit_write_args_inplace(unit, [[BC.LOAD_MEM, slots[5]]])
        compiler.Compiler.emit_load_k(unit, k)
        compiler.Compiler.emit_apply_k(unit)

    return BuiltinSymbol(
        source="+",
        path=TreePathEntry.for_builtin("+<string>").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.STRING,
                PrimitiveLanguageType.STRING,
                FunctionLanguageType([PrimitiveLanguageType.STRING], typevar_emitter()),
            ],
            PrimitiveLanguageType.VOID,
        ),
        emit_inplace=None,
        emit_lambda=LambdaEmitter(
            slots=[
                "STR1",
                "STR2",
                "LEN1",
                "LEN2",
                "NEW_LEN",
                "NEW_STR",
                "I",
                "SRC",
                "DEST",
            ],
            bytecode_emitter=emit_add_string_bytecode,
        ),
    )


def builtin_string_length():
    """`(string-length s)` -- длина pstr (читает первое слово через LOAD_IND_MEM)."""
    return BuiltinSymbol(
        source="string-length",
        path=TreePathEntry.for_builtin("string-length").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [PrimitiveLanguageType.STRING],
            PrimitiveLanguageType.INTEGER,
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend(
            [
                BC.LOAD_IND_MEM,
                args[0],
                BC.STORE_MEM,
                slot,
            ]
        ),
        emit_lambda=None,
    )


def builtin_string_ref():
    """`(string-ref s i)` -- i-й символ pstr как INTEGER. Адрес = s + (i+1)*WORD_LEN."""

    def emit(unit, slot, *args):
        unit.bytecode.extend(
            [
                BC.LOAD_MEM,
                args[1],
                BC.ADD_IMM,
                1,
                BC.MUL_IMM,
                compiler.Memory.WORD_LEN,
                BC.ADD_MEM,
                args[0],
                BC.STORE_MEM,
                slot,
                BC.LOAD_IND_MEM,
                slot,
                BC.STORE_MEM,
                slot,
            ]
        )

    return BuiltinSymbol(
        source="string-ref",
        path=TreePathEntry.for_builtin("string-ref").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [PrimitiveLanguageType.STRING, PrimitiveLanguageType.INTEGER],
            PrimitiveLanguageType.INTEGER,
        ),
        emit_inplace=emit,
        emit_lambda=None,
    )


def builtin_string_set():
    """`(string-set! s i v)` -- записать символ v в позицию i pstr. VOID.

    Возвращает 0 (как маркер VOID). Используется для мутации строк (в первую
    очередь -- результат `input` или результат `make-string`).
    """

    def emit(unit, slot, *args):
        unit.bytecode.extend(
            [
                BC.LOAD_MEM,
                args[1],
                BC.ADD_IMM,
                1,
                BC.MUL_IMM,
                compiler.Memory.WORD_LEN,
                BC.ADD_MEM,
                args[0],
                BC.STORE_MEM,
                slot,
                BC.LOAD_MEM,
                args[2],
                BC.STORE_IND_MEM,
                slot,
                BC.LOAD_IMM,
                0,
                BC.STORE_MEM,
                slot,
            ]
        )

    return BuiltinSymbol(
        source="string-set!",
        path=TreePathEntry.for_builtin("string-set!").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.STRING,
                PrimitiveLanguageType.INTEGER,
                PrimitiveLanguageType.INTEGER,
            ],
            PrimitiveLanguageType.INTEGER,
        ),
        emit_inplace=emit,
        emit_lambda=None,
    )


def builtin_sort_string():
    """`(sort-string! s)` -- bubble-sort PSTR in-place. CISC-style: одна
    "инструкция" языка разворачивается в десятки циклов на bytecode-уровне.

    Возвращает VOID (через 0), мутирует s по месту. Сложность O(n²) тактов.
    """

    def emit(unit, slots, k, *args):
        bytecode = unit.bytecode
        s_arg = args[0]

        # Локальные слоты: 0=N, 1=II, 2=J, 3=A_PTR, 4=B_PTR, 5=A, 6=B
        N, II, J, A_PTR, B_PTR, A, B = (slots[i] for i in range(7))

        # N = *s (длина строки)
        bytecode.extend(
            [
                BC.LOAD_IND_MEM,
                s_arg,
                BC.STORE_MEM,
                N,
                BC.LOAD_IMM,
                0,
                BC.STORE_MEM,
                II,
            ]
        )

        outer_start = len(bytecode) * compiler.Memory.WORD_LEN
        # if I >= N -> exit outer
        bytecode.extend(
            [
                BC.LOAD_MEM,
                II,
                BC.LT_MEM,
                N,
                BC.JMP_T,  # jump to body
            ]
        )
        outer_jmp_continue_idx = len(bytecode)
        bytecode.append(0)
        bytecode.extend([BC.JMP])
        outer_jmp_exit_idx = len(bytecode)
        bytecode.append(0)
        bytecode[outer_jmp_continue_idx] = len(bytecode) * compiler.Memory.WORD_LEN

        # J = 0
        bytecode.extend([BC.LOAD_IMM, 0, BC.STORE_MEM, J])

        inner_start = len(bytecode) * compiler.Memory.WORD_LEN
        # if J >= N - 1 -> exit inner
        bytecode.extend(
            [
                BC.LOAD_MEM,
                N,
                BC.SUB_IMM,
                1,
                BC.SUB_MEM,
                J,
                BC.JMP_T,  # jump to inner body if (N - 1 - J) != 0
            ]
        )
        inner_jmp_continue_idx = len(bytecode)
        bytecode.append(0)
        bytecode.extend([BC.JMP])
        inner_jmp_exit_idx = len(bytecode)
        bytecode.append(0)
        bytecode[inner_jmp_continue_idx] = len(bytecode) * compiler.Memory.WORD_LEN

        # A_PTR = s + (J + 1) * WORD_LEN  (адрес символа s[J] в pstr)
        bytecode.extend(
            [
                BC.LOAD_MEM,
                J,
                BC.ADD_IMM,
                1,
                BC.MUL_IMM,
                compiler.Memory.WORD_LEN,
                BC.ADD_MEM,
                s_arg,
                BC.STORE_MEM,
                A_PTR,
                # B_PTR = A_PTR + WORD_LEN
                BC.ADD_IMM,
                compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                B_PTR,
                # A = *A_PTR
                BC.LOAD_IND_MEM,
                A_PTR,
                BC.STORE_MEM,
                A,
                # B = *B_PTR
                BC.LOAD_IND_MEM,
                B_PTR,
                BC.STORE_MEM,
                B,
                # if A <= B -- skip swap
                BC.LOAD_MEM,
                A,
                BC.LE_MEM,
                B,
                BC.JMP_T,
            ]
        )
        skip_swap_idx = len(bytecode)
        bytecode.append(0)
        # *A_PTR = B
        bytecode.extend(
            [
                BC.LOAD_MEM,
                B,
                BC.STORE_IND_MEM,
                A_PTR,
                BC.LOAD_MEM,
                A,
                BC.STORE_IND_MEM,
                B_PTR,
            ]
        )
        bytecode[skip_swap_idx] = len(bytecode) * compiler.Memory.WORD_LEN
        # J += 1
        bytecode.extend(
            [
                BC.LOAD_MEM,
                J,
                BC.ADD_IMM,
                1,
                BC.STORE_MEM,
                J,
                BC.JMP,
                inner_start,
            ]
        )
        bytecode[inner_jmp_exit_idx] = len(bytecode) * compiler.Memory.WORD_LEN

        # I += 1
        bytecode.extend(
            [
                BC.LOAD_MEM,
                II,
                BC.ADD_IMM,
                1,
                BC.STORE_MEM,
                II,
                BC.JMP,
                outer_start,
            ]
        )
        bytecode[outer_jmp_exit_idx] = len(bytecode) * compiler.Memory.WORD_LEN

        # Возврат VOID + applied continuation
        compiler.Compiler.emit_write_args_inplace(unit, [[BC.LOAD_IMM, 0]])
        compiler.Compiler.emit_load_k(unit, k)
        compiler.Compiler.emit_apply_k(unit)

    return BuiltinSymbol(
        source="sort-string!",
        path=TreePathEntry.for_builtin("sort-string!").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.STRING,
                FunctionLanguageType([PrimitiveLanguageType.VOID], typevar_emitter()),
            ],
            PrimitiveLanguageType.VOID,
        ),
        emit_inplace=None,
        emit_lambda=LambdaEmitter(
            slots=["N", "I", "J", "A_PTR", "B_PTR", "A", "B"],
            bytecode_emitter=emit,
        ),
    )


def builtin_strings() -> list[BuiltinSymbol]:
    """Return all string-related builtin symbols."""
    return [
        builtin_to_integer_unchecked_string(),
        builtin_concat_string(),
        builtin_string_length(),
        builtin_string_ref(),
        builtin_string_set(),
        builtin_sort_string(),
    ]
