"""Ввод/вывод: (print ...) и (input).

print пишет символы в PORT_OUT; input читает строку из буфера,
заполняемого обработчиком прерывания при trap-вводе.
"""

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


def builtin_print_string():
    def emit_print_string_bytecode(unit, slots, k, *args):
        bytecode = unit.bytecode

        # 1. Инициализация
        bytecode.extend(
            [
                BC.LOAD_IMM,
                0,
                BC.STORE_MEM,
                slots[0],  # PRINTED_COUNT = 0
                BC.LOAD_MEM,
                args[0],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[1],  # CURRENT_CHAR_PTR
            ]
        )

        # 2. Цикл печати
        label_compare = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode.extend([BC.LOAD_IND_MEM, args[0], BC.EQ_MEM, slots[0], BC.JMP_T, -1])
        jmp_t_index = len(bytecode) - 1

        bytecode.extend(
            [
                BC.LOAD_IND_MEM,
                slots[1],
                BC.STORE_MEM,
                compiler.Memory.PORT_OUT,
                BC.LOAD_MEM,
                slots[0],
                BC.ADD_IMM,
                1,
                BC.STORE_MEM,
                slots[0],
                BC.LOAD_MEM,
                slots[1],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[1],
                BC.JMP,
                label_compare,
            ]
        )
        bytecode[jmp_t_index] = len(bytecode) * compiler.Memory.WORD_LEN

        # 3. Выход с VOID
        compiler.Compiler.emit_write_args_inplace(unit, [[BC.LOAD_IMM, 0]])
        compiler.Compiler.emit_load_k(unit, k)
        compiler.Compiler.emit_apply_k(unit)

    return BuiltinSymbol(
        source="print",
        path=TreePathEntry.for_builtin("print<string>").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.STRING,
                FunctionLanguageType([PrimitiveLanguageType.VOID], typevar_emitter()),
            ],
            PrimitiveLanguageType.VOID,
        ),
        emit_inplace=None,
        emit_lambda=LambdaEmitter(
            slots=["PRINTED_COUNT", "CURRENT_CHAR_PTR"],
            bytecode_emitter=emit_print_string_bytecode,
        ),
    )


def builtin_input_string():
    def emit_input_string_bytecode(unit, slots, k, *args):
        bytecode = unit.bytecode

        # 1. Инициализация
        bytecode.extend([BC.LOAD_IMM, 0, BC.STORE_MEM, slots[2]])  # COUNTER = 0

        # 2. Ожидание длины строки
        label_wait_string_length = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode.extend(
            [
                BC.LOAD_IND_MEM,
                slots[0],
                BC.EQ_IMM,
                0,
                BC.JMP_T,
                label_wait_string_length,
            ]
        )

        # Прочитали длину
        bytecode.extend(
            [
                BC.LOAD_IND_MEM,
                slots[0],
                BC.STORE_MEM,
                slots[1],  # RECEIVED_LENGTH
                BC.LOAD_IMM,
                0,
                BC.STORE_IND_MEM,
                slots[0],
                BC.LOAD_MEM,
                slots[0],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[0],
            ]
        )

        # 3. Выделение памяти в HEAP
        bytecode.extend(
            [
                BC.LOAD_MEM,
                compiler.Memory.HEAP,
                BC.STORE_MEM,
                slots[3],  # RESULT_STRING_PTR
                BC.LOAD_MEM,
                slots[1],
                BC.STORE_IND_MEM,
                slots[3],  # *RESULT_STRING_PTR = RECEIVED_LENGTH
                BC.LOAD_MEM,
                compiler.Memory.HEAP,
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
            ]
        )
        # HEAP += RECEIVED_LENGTH * WORD_LEN
        for _ in range(compiler.Memory.WORD_LEN):
            bytecode.extend([BC.ADD_MEM, slots[1]])
        bytecode.extend([BC.STORE_MEM, compiler.Memory.HEAP])

        # 4. Цикл ожидания символов
        label_wait_string_all_chars = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode.extend([BC.LOAD_MEM, slots[2], BC.EQ_MEM, slots[1], BC.JMP_T, -1])
        jmp_t_index = len(bytecode) - 1

        label_wait_string_char = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode.extend(
            [
                BC.LOAD_IND_MEM,
                slots[0],
                BC.EQ_IMM,
                0,
                BC.JMP_T,
                label_wait_string_char,
            ]
        )

        # Получили символ
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[3],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[3],
                BC.LOAD_IND_MEM,
                slots[0],
                BC.STORE_IND_MEM,
                slots[3],
                BC.LOAD_IMM,
                0,
                BC.STORE_IND_MEM,
                slots[0],
                BC.LOAD_MEM,
                slots[0],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[0],
                BC.LOAD_MEM,
                slots[2],
                BC.ADD_IMM,
                1,
                BC.STORE_MEM,
                slots[2],  # COUNTER++
            ]
        )

        bytecode.extend([BC.JMP, label_wait_string_all_chars])
        bytecode[jmp_t_index] = len(bytecode) * compiler.Memory.WORD_LEN

        # 5. Выход с результирующей строкой
        write_args = [BC.LOAD_MEM, slots[3]]
        # RESULT_STRING_PTR -= RECEIVED_LENGTH * WORD_LEN
        for _ in range(compiler.Memory.WORD_LEN):
            write_args.extend([BC.SUB_MEM, slots[1]])
        compiler.Compiler.emit_write_args_inplace(unit, [write_args])
        compiler.Compiler.emit_load_k(unit, k)
        compiler.Compiler.emit_apply_k(unit)

    return BuiltinSymbol(
        source="input",
        path=TreePathEntry.for_builtin("input<string>").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [FunctionLanguageType([PrimitiveLanguageType.STRING], typevar_emitter())],
            PrimitiveLanguageType.VOID,
        ),
        emit_inplace=None,
        emit_lambda=LambdaEmitter(
            slots=["NEXT_BUF_PTR", "RECEIVED_LENGTH", "COUNTER", "RESULT_STRING_PTR"],
            bytecode_emitter=emit_input_string_bytecode,
        ),
    )


def builtin_io() -> list[BuiltinSymbol]:
    """Return all non-generic I/O builtin symbols.

    Note: print<string> is registered via generic_builtin_symbols_builders() instead.
    """
    return [
        builtin_input_string(),
    ]
