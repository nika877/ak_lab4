from dataclasses import dataclass
from typing import Protocol
from lang.compiler.bytecode import BC
from lang.lang_type import FunctionLanguageType, LanguageType, LanguageTypeVar, PrimitiveLanguageType
from .qualname import BuiltinQualName, BuiltinSymbol, BuiltinSymbolOverload, CodegenSlot, GenericBuiltinQualName, GenericBuiltinSymbol, GenericBuiltinSymbolBuilderProtocol, LanguageTypeVarEmitter, TreePath, TreePathEntry
import lang.compiler as compiler


class BuiltinQualNameInstantiator(Protocol):
    def __call__(self) -> BuiltinQualName:
        ...


# halt_integer halt_string ... ?
def builtin_halt():
    return BuiltinSymbol(
        source="halt",
        path=TreePathEntry.for_builtin("halt").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [typevar_emitter()],
            PrimitiveLanguageType.VOID
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend([
            BC.HALT
        ]),
        emit_lambda=lambda unit, k, *args: unit.bytecode.extend([
            BC.LOAD_MEM,
            k,
            BC.HALT
        ])
    )


def builtin_print_integer():
    return BuiltinSymbol(
        source="print",
        path=TreePathEntry.for_builtin("print<integer>").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [PrimitiveLanguageType.INTEGER],
            PrimitiveLanguageType.VOID
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend([
            BC.LOAD_MEM,
            args[0],
            BC.INT_PRINT,
            BC.LOAD_IMM,
            0,
            BC.STORE_MEM,
            slot
        ]),
        emit_lambda=None
    )


def builtin_print_string():
    return BuiltinSymbol(
        source="print",
        path=TreePathEntry.for_builtin("print<string>").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [PrimitiveLanguageType.STRING],
            PrimitiveLanguageType.VOID
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend([
            BC.LOAD_MEM,
            args[0],
            BC.INT_PRINT,
            BC.LOAD_IMM,
            0,
            BC.STORE_MEM,
            slot
        ]),
        emit_lambda=None
    )


def builtin_print_boolean():
    return BuiltinSymbol(
        source="print",
        path=TreePathEntry.for_builtin("print<boolean>").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [PrimitiveLanguageType.BOOLEAN],
            PrimitiveLanguageType.VOID
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend([
            BC.LOAD_MEM,
            args[0],
            BC.INT_PRINT,
            BC.LOAD_IMM,
            0,
            BC.STORE_MEM,
            slot
        ]),
        emit_lambda=None
    )


def builtin_add_integer_2():
    return BuiltinSymbol(
        source="+",
        path=TreePathEntry.for_builtin("+<integer>#2").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [PrimitiveLanguageType.INTEGER, PrimitiveLanguageType.INTEGER],
            PrimitiveLanguageType.INTEGER
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend([
            BC.LOAD_MEM,
            args[0],
            BC.ADD_MEM,
            args[1],
            BC.STORE_MEM,
            slot
        ]),
        emit_lambda=None
    )


def builtin_add_integer_2_lambda():
    return BuiltinSymbol(
        source="+",
        path=TreePathEntry.for_builtin("+<integer>#2.lambda").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.INTEGER,
                PrimitiveLanguageType.INTEGER,
                FunctionLanguageType([PrimitiveLanguageType.INTEGER], typevar_emitter())
            ],
            PrimitiveLanguageType.VOID
        ),
        emit_inplace=None,
        emit_lambda=lambda unit, k, *args: (
            compiler.Compiler.emit_write_k_args_inplace(unit, [
                [
                    BC.LOAD_MEM,
                    args[0],
                    BC.ADD_MEM,
                    args[1],
                ]
            ]),
            compiler.Compiler.emit_load_k(unit, k),
            compiler.Compiler.emit_apply_k(unit)
        )
    )


def builtin_add_integer_3():
    return BuiltinSymbol(
        source="+",
        path=TreePathEntry.for_builtin("+<integer>#3").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.INTEGER,
                PrimitiveLanguageType.INTEGER,
                PrimitiveLanguageType.INTEGER
            ],
            PrimitiveLanguageType.INTEGER
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend([
            BC.LOAD_MEM,
            args[0],
            BC.ADD_MEM,
            args[1],
            BC.ADD_MEM,
            args[2],
            BC.STORE_MEM,
            slot
        ]),
        emit_lambda=None
    )


def builtin_add_string():
    return BuiltinSymbol(
        source="+",
        path=TreePathEntry.for_builtin("+<string>").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.STRING,
                PrimitiveLanguageType.STRING,
            ],
            PrimitiveLanguageType.STRING
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend([
            BC.LOAD_IMM,
            0,
            BC.STORE_MEM,
            slot
        ]),
        emit_lambda=None
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
            PrimitiveLanguageType.INTEGER
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend([
            BC.LOAD_MEM,
            args[0],
            BC.SUB_MEM,
            args[1],
            BC.STORE_MEM,
            slot
        ]),
        emit_lambda=None
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
            PrimitiveLanguageType.INTEGER
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend([
            BC.LOAD_MEM,
            args[0],
            BC.MUL_MEM,
            args[1],
            BC.STORE_MEM,
            slot
        ]),
        emit_lambda=None
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
            PrimitiveLanguageType.BOOLEAN
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend([
            BC.LOAD_MEM,
            args[0],
            BC.LE_MEM,
            args[1],
            BC.STORE_MEM,
            slot
        ]),
        emit_lambda=None
    )


def builtin_symbols() -> list[BuiltinSymbol]:
    return [
        builtin_halt(),
        builtin_sub(),
        builtin_mul(),
        builtin_le()
    ]


@dataclass(frozen=True)
class GenericBuiltinSymbolBuilder(GenericBuiltinSymbolBuilderProtocol):
    source: str
    path: TreePath
    entries: list[BuiltinSymbol]

    def __post_init__(self):
        assert len(self.entries) > 0

    def __call__(self, typevar_emitter: LanguageTypeVarEmitter) -> GenericBuiltinSymbol:
        source = self.entries[0].source
        overloads = []

        for entry in self.entries:
            assert source == entry.source
            overloads.append(BuiltinSymbolOverload(
                entry.lang_type_builder(typevar_emitter),
                entry
            ))

        return GenericBuiltinSymbol(
            source,
            overloads
        )


def generic_builtin_symbols_builders() -> list[GenericBuiltinSymbolBuilder]:
    return [
        GenericBuiltinSymbolBuilder(
            "+",
            TreePathEntry.for_builtin("+<T>").as_entire_tree_path(),
            [
                builtin_add_integer_2(),
                builtin_add_integer_3(),
                builtin_add_string(),
                builtin_add_integer_2_lambda()
            ]
        ),
        GenericBuiltinSymbolBuilder(
            "print",
            TreePathEntry.for_builtin("print<T>").as_entire_tree_path(),
            [
                builtin_print_integer(),
                builtin_print_boolean(),
                builtin_print_string(),
            ]
        )
    ]
