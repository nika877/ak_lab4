"""Логические и сравнительные встроенные: and, or, ==, <, > и т.д."""

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


def builtin_halt():
    return BuiltinSymbol(
        source="halt",
        path=TreePathEntry.for_builtin("halt").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [typevar_emitter()], PrimitiveLanguageType.VOID
        ),
        emit_inplace=None,
        emit_lambda=LambdaEmitter(
            slots=[],
            bytecode_emitter=lambda unit, slots, k, *args: unit.bytecode.extend(
                [BC.LOAD_MEM, k, BC.HALT]
            ),
        ),
    )


def builtin_and():
    return BuiltinSymbol(
        source="and",
        path=TreePathEntry.for_builtin("and").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [PrimitiveLanguageType.BOOLEAN, PrimitiveLanguageType.BOOLEAN],
            PrimitiveLanguageType.BOOLEAN,
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend(
            [BC.LOAD_MEM, args[0], BC.AND_MEM, args[1], BC.STORE_MEM, slot]
        ),
        emit_lambda=None,
    )


def builtin_or():
    return BuiltinSymbol(
        source="or",
        path=TreePathEntry.for_builtin("or").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [PrimitiveLanguageType.BOOLEAN, PrimitiveLanguageType.BOOLEAN],
            PrimitiveLanguageType.BOOLEAN,
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend(
            [BC.LOAD_MEM, args[0], BC.OR_MEM, args[1], BC.STORE_MEM, slot]
        ),
        emit_lambda=None,
    )


def builtin_eq():
    return BuiltinSymbol(
        source="==",
        path=TreePathEntry.for_builtin("==").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.INTEGER,
                PrimitiveLanguageType.INTEGER,
            ],
            PrimitiveLanguageType.BOOLEAN,
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend(
            [BC.LOAD_MEM, args[0], BC.EQ_MEM, args[1], BC.STORE_MEM, slot]
        ),
        emit_lambda=None,
    )


def builtin_lt():
    return BuiltinSymbol(
        source="<",
        path=TreePathEntry.for_builtin("<").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.INTEGER,
                PrimitiveLanguageType.INTEGER,
            ],
            PrimitiveLanguageType.BOOLEAN,
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend(
            [BC.LOAD_MEM, args[0], BC.LT_MEM, args[1], BC.STORE_MEM, slot]
        ),
        emit_lambda=None,
    )


def builtin_le():
    return BuiltinSymbol(
        source="<=",
        path=TreePathEntry.for_builtin("<=").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.INTEGER,
                PrimitiveLanguageType.INTEGER,
            ],
            PrimitiveLanguageType.BOOLEAN,
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend(
            [BC.LOAD_MEM, args[0], BC.LE_MEM, args[1], BC.STORE_MEM, slot]
        ),
        emit_lambda=None,
    )


def builtin_gt():
    return BuiltinSymbol(
        source=">",
        path=TreePathEntry.for_builtin(">").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.INTEGER,
                PrimitiveLanguageType.INTEGER,
            ],
            PrimitiveLanguageType.BOOLEAN,
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend(
            [BC.LOAD_MEM, args[0], BC.GT_MEM, args[1], BC.STORE_MEM, slot]
        ),
        emit_lambda=None,
    )


def builtin_bit_and():
    """`(bit-and a b)` -- побитовое AND для int32 (для маски нижних бит, и т.д.)."""
    return BuiltinSymbol(
        source="bit-and",
        path=TreePathEntry.for_builtin("bit-and").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [PrimitiveLanguageType.INTEGER, PrimitiveLanguageType.INTEGER],
            PrimitiveLanguageType.INTEGER,
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend(
            [BC.LOAD_MEM, args[0], BC.AND_MEM, args[1], BC.STORE_MEM, slot]
        ),
        emit_lambda=None,
    )


def builtin_bit_or():
    """`(bit-or a b)` -- побитовое OR для int32."""
    return BuiltinSymbol(
        source="bit-or",
        path=TreePathEntry.for_builtin("bit-or").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [PrimitiveLanguageType.INTEGER, PrimitiveLanguageType.INTEGER],
            PrimitiveLanguageType.INTEGER,
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend(
            [BC.LOAD_MEM, args[0], BC.OR_MEM, args[1], BC.STORE_MEM, slot]
        ),
        emit_lambda=None,
    )


def builtin_lsr():
    """`(lsr a n)` -- логический сдвиг вправо (нули в старшие биты)."""
    return BuiltinSymbol(
        source="lsr",
        path=TreePathEntry.for_builtin("lsr").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [PrimitiveLanguageType.INTEGER, PrimitiveLanguageType.INTEGER],
            PrimitiveLanguageType.INTEGER,
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend(
            [BC.LOAD_MEM, args[0], BC.LSR_MEM, args[1], BC.STORE_MEM, slot]
        ),
        emit_lambda=None,
    )


def builtin_asl():
    """`(asl a n)` -- арифметический/логический сдвиг влево."""
    return BuiltinSymbol(
        source="asl",
        path=TreePathEntry.for_builtin("asl").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [PrimitiveLanguageType.INTEGER, PrimitiveLanguageType.INTEGER],
            PrimitiveLanguageType.INTEGER,
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend(
            [BC.LOAD_MEM, args[0], BC.ASL_MEM, args[1], BC.STORE_MEM, slot]
        ),
        emit_lambda=None,
    )


def builtin_logic() -> list[BuiltinSymbol]:
    """Return all logic (boolean, comparison, and control) builtin symbols."""
    return [
        builtin_halt(),
        builtin_and(),
        builtin_or(),
        builtin_eq(),
        builtin_lt(),
        builtin_le(),
        builtin_gt(),
        builtin_bit_and(),
        builtin_bit_or(),
        builtin_lsr(),
        builtin_asl(),
    ]
