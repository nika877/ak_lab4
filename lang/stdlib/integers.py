"""Встроенные операции над целыми числами (INTEGER).

Атомарные (+, -, *, /) вставляются inline в байткод.
Сложные (to-string для int) — отдельные lambda-фрагменты с циклами.
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


def builtin_to_string_integer():
    def emit_to_string_integer_bytecode(unit, slots, k, *args):
        bytecode = unit.bytecode

        bytecode.extend(
            [
                BC.LOAD_MEM,
                args[0],
                BC.STORE_MEM,
                slots[0],  # INPUT_VAL
                BC.LOAD_IMM,
                0,
                BC.STORE_MEM,
                slots[1],  # IS_NEG = 0
                BC.STORE_MEM,
                slots[4],  # DIGIT_COUNT = 0
                BC.LOAD_MEM,
                compiler.Memory.HEAP,
                BC.STORE_MEM,
                slots[3],  # START_PTR
                BC.ADD_IMM,
                12 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                compiler.Memory.HEAP,
                BC.LOAD_MEM,
                slots[3],
                BC.ADD_IMM,
                11 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[2],  # WRITE_PTR = START_PTR + 11
            ]
        )

        bytecode.extend([BC.LOAD_MEM, slots[0], BC.GE_IMM, 0, BC.JMP_T])
        jmp_abs_pos = len(bytecode)
        bytecode.append(0)

        bytecode.extend(
            [
                BC.LOAD_IMM,
                1,
                BC.STORE_MEM,
                slots[1],
                BC.LOAD_IMM,
                0,
                BC.SUB_MEM,
                slots[0],
                BC.STORE_MEM,
                slots[0],
            ]
        )

        loop_start = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[jmp_abs_pos] = loop_start
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[0],
                BC.MOD_IMM,
                10,
                BC.ADD_IMM,
                48,
                BC.STORE_IND_MEM,
                slots[2],
                BC.LOAD_MEM,
                slots[2],
                BC.SUB_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[2],
                BC.LOAD_MEM,
                slots[4],
                BC.ADD_IMM,
                1,
                BC.STORE_MEM,
                slots[4],
                BC.LOAD_MEM,
                slots[0],
                BC.DIV_IMM,
                10,
                BC.STORE_MEM,
                slots[0],
                BC.GT_IMM,
                0,
                BC.JMP_T,
                loop_start,
            ]
        )

        bytecode.extend([BC.LOAD_MEM, slots[1], BC.EQ_IMM, 0, BC.JMP_T])
        jmp_minus_pos = len(bytecode)
        bytecode.append(0)
        bytecode.extend(
            [
                BC.LOAD_IMM,
                45,
                BC.STORE_IND_MEM,
                slots[2],
                BC.LOAD_MEM,
                slots[2],
                BC.SUB_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[2],
                BC.LOAD_MEM,
                slots[4],
                BC.ADD_IMM,
                1,
                BC.STORE_MEM,
                slots[4],
            ]
        )
        bytecode[jmp_minus_pos] = len(bytecode) * compiler.Memory.WORD_LEN

        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[4],
                BC.STORE_IND_MEM,
                slots[2],
            ]
        )

        compiler.Compiler.emit_write_args_inplace(unit, [[BC.LOAD_MEM, slots[2]]])
        compiler.Compiler.emit_load_k(unit, k)
        compiler.Compiler.emit_apply_k(unit)

    return BuiltinSymbol(
        source="to-string",
        path=TreePathEntry.for_builtin("to-string<integer>").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.INTEGER,
                FunctionLanguageType([PrimitiveLanguageType.STRING], typevar_emitter()),
            ],
            PrimitiveLanguageType.VOID,
        ),
        emit_inplace=None,
        emit_lambda=LambdaEmitter(
            slots=["INPUT_VAL", "IS_NEG", "WRITE_PTR", "START_PTR", "DIGIT_COUNT"],
            bytecode_emitter=emit_to_string_integer_bytecode,
        ),
    )


def builtin_add_integer_2():
    return BuiltinSymbol(
        source="+",
        path=TreePathEntry.for_builtin("+<integer>#2").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [PrimitiveLanguageType.INTEGER, PrimitiveLanguageType.INTEGER],
            PrimitiveLanguageType.INTEGER,
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend(
            [BC.LOAD_MEM, args[0], BC.ADD_MEM, args[1], BC.STORE_MEM, slot]
        ),
        emit_lambda=None,
    )


def builtin_add_integer_3():
    return BuiltinSymbol(
        source="+",
        path=TreePathEntry.for_builtin("+<integer>#3").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.INTEGER,
                PrimitiveLanguageType.INTEGER,
                PrimitiveLanguageType.INTEGER,
            ],
            PrimitiveLanguageType.INTEGER,
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend(
            [
                BC.LOAD_MEM,
                args[0],
                BC.ADD_MEM,
                args[1],
                BC.ADD_MEM,
                args[2],
                BC.STORE_MEM,
                slot,
            ]
        ),
        emit_lambda=None,
    )


def builtin_add_integer_2_lambda():
    def emit_add_integer_2_lambda_bytecode(unit, slots, k, *args):
        compiler.Compiler.emit_write_args_inplace(
            unit,
            [
                [
                    BC.LOAD_MEM,
                    args[0],
                    BC.ADD_MEM,
                    args[1],
                ]
            ],
        )
        compiler.Compiler.emit_load_k(unit, k)
        compiler.Compiler.emit_apply_k(unit)

    return BuiltinSymbol(
        source="+",
        path=TreePathEntry.for_builtin("+<integer>#2.lambda").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.INTEGER,
                PrimitiveLanguageType.INTEGER,
                FunctionLanguageType([PrimitiveLanguageType.INTEGER], typevar_emitter()),
            ],
            PrimitiveLanguageType.VOID,
        ),
        emit_inplace=None,
        emit_lambda=LambdaEmitter(
            slots=[],
            bytecode_emitter=emit_add_integer_2_lambda_bytecode,
        ),
    )


def builtin_sub():
    return BuiltinSymbol(
        source="-",
        path=TreePathEntry.for_builtin("-").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.INTEGER,
                PrimitiveLanguageType.INTEGER,
            ],
            PrimitiveLanguageType.INTEGER,
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend(
            [BC.LOAD_MEM, args[0], BC.SUB_MEM, args[1], BC.STORE_MEM, slot]
        ),
        emit_lambda=None,
    )


def builtin_mul():
    return BuiltinSymbol(
        source="*",
        path=TreePathEntry.for_builtin("*").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.INTEGER,
                PrimitiveLanguageType.INTEGER,
            ],
            PrimitiveLanguageType.INTEGER,
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend(
            [BC.LOAD_MEM, args[0], BC.MUL_MEM, args[1], BC.STORE_MEM, slot]
        ),
        emit_lambda=None,
    )


def builtin_div():
    return BuiltinSymbol(
        source="/",
        path=TreePathEntry.for_builtin("/").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.INTEGER,
                PrimitiveLanguageType.INTEGER,
            ],
            PrimitiveLanguageType.INTEGER,
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend(
            [BC.LOAD_MEM, args[0], BC.DIV_MEM, args[1], BC.STORE_MEM, slot]
        ),
        emit_lambda=None,
    )


def builtin_mod_integer():
    return BuiltinSymbol(
        source="mod",
        path=TreePathEntry.for_builtin("mod<integer>").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [PrimitiveLanguageType.INTEGER, PrimitiveLanguageType.INTEGER],
            PrimitiveLanguageType.INTEGER,
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend(
            [BC.LOAD_MEM, args[0], BC.MOD_MEM, args[1], BC.STORE_MEM, slot]
        ),
        emit_lambda=None,
    )


def builtin_integers() -> list[BuiltinSymbol]:
    """Return all non-generic integer builtin symbols.

    Note: to-string<integer> and +<integer> variants are registered
    via generic_builtin_symbols_builders() instead.
    """
    return [
        builtin_sub(),
        builtin_mul(),
        builtin_div(),
        builtin_mod_integer(),
    ]
