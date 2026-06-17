"""Статическая раскладка памяти виртуальной машины.

Память — единое 32-битное адресное пространство (фон Нейман):
  0x00 — HEAP (указатель на свободную ячейку кучи)
  0x04 — K (текущее продолжение — continuation)
  0x08 — PORT_IN, 0x0C — PORT_OUT (ввод/вывод)
  0x10.. — ARG_SLOT_1..16 (аргументы при вызове)
  далее — слоты переменных, строк, констант
  в конце — байткод программы
"""

from __future__ import annotations

from collections.abc import Iterable
from ctypes import c_float, c_int32, c_uint32
from dataclasses import dataclass
from typing import assert_never, cast

from lang.exceptions import CompilerError
from lang.lang_type import FunctionLanguageType, PrimitiveLanguageType
from lang.parser.qualname import (
    BaseConstQualName,
    BuiltinQualName,
    DoubleConstQualName,
    ProjectionQualName,
    StringConstQualName,
    TreePath,
    TreePathEntry,
    UsageQualName,
)
from lang.parser.qualname_assign import VirtualToken
from lang.parser.s_expr import SExprDefun, SExprLambda

from .bytecode import BytecodeUnit
from .inferrer import InferrerResult


@dataclass(init=False)
class MemorySlot32:
    """Один слот памяти (4 байта): привязан к пути в дереве программы."""

    path: TreePath
    _value: c_int32

    def __init__(self, path: TreePath, value: int | c_int32 | c_uint32 | c_float):
        self.path = path
        self.value = value

    @property
    def value(self) -> c_int32:
        return self._value

    @value.setter
    def value(self, val: int | c_int32 | c_uint32 | c_float):
        match val:
            case int() as val:
                self._value = c_int32(val)
            case c_int32() as val:
                self._value = val
            case c_uint32() as val:
                self._value = c_int32.from_buffer_copy(val)
            case c_float() as val:
                self._value = c_int32.from_buffer_copy(val)
            case never:
                assert_never(never)

    def __str__(self):
        return f"slot[{self.path} = {self.value}]"


@dataclass
class LookupCaptureEntry:
    variable_path: TreePath
    slot: int


@dataclass
class Memory:
    """Карта памяти: слоты, таблицы поиска, захваты замыканий."""

    WORD_LEN = 4  # размер одного слова в байтах

    MAX_ARITY = 16  # максимум аргументов у функции

    @classmethod
    def arg_slots(cls):
        """Генератор адресов ARG_SLOT_1 .. ARG_SLOT_16."""
        for i in range(cls.MAX_ARITY):
            yield (4 + i) * cls.WORD_LEN
        raise CompilerError(f"Maximum arity of {cls.MAX_ARITY} was superseded")

    @classmethod
    def default_int_handler_input_buf_slots(cls):
        base_idx = 4 + cls.MAX_ARITY + 1 + 1
        for i in range(32):
            yield (base_idx + i) * cls.WORD_LEN

    # Фиксированные системные ячейки (см. README — организация памяти)
    HEAP = 0 * WORD_LEN
    K = 1 * WORD_LEN
    PORT_IN = 2 * WORD_LEN
    PORT_OUT = 3 * WORD_LEN
    ARG_SLOT_1 = 4 * WORD_LEN
    ARG_SLOT_2 = 5 * WORD_LEN
    ARG_SLOT_3 = 6 * WORD_LEN
    ARG_SLOT_4 = 7 * WORD_LEN
    ARG_SLOT_5 = 8 * WORD_LEN
    ARG_SLOT_6 = 9 * WORD_LEN
    ARG_SLOT_7 = 10 * WORD_LEN
    ARG_SLOT_8 = 11 * WORD_LEN
    ARG_SLOT_9 = 12 * WORD_LEN
    ARG_SLOT_10 = 13 * WORD_LEN
    ARG_SLOT_11 = 14 * WORD_LEN
    ARG_SLOT_12 = 15 * WORD_LEN
    ARG_SLOT_13 = 16 * WORD_LEN
    ARG_SLOT_14 = 17 * WORD_LEN
    ARG_SLOT_15 = 18 * WORD_LEN
    ARG_SLOT_16 = 19 * WORD_LEN
    INT_VECTOR_INPUT = 20 * WORD_LEN
    DEFAULT_INT_HANDLER_INPUT_NEXT_BUF_IDX = 21 * WORD_LEN

    @classmethod
    def INITIAL_NEXT_FREE_CELL(cls):
        slots_count = len(list(cls.default_int_handler_input_buf_slots()))
        return (
            cls.DEFAULT_INT_HANDLER_INPUT_NEXT_BUF_IDX + slots_count * cls.WORD_LEN + cls.WORD_LEN
        )

    slots: list[MemorySlot32]
    lookup_slots: dict[TreePath, int]
    lookup_args: dict[TreePath, list[int]]
    lookup_captures_sources: dict[TreePath, list[int]]
    lookup_captures_destinations: dict[TreePath, list[int]]
    lookup_builtin_lambda_slots: dict[TreePath, list[int]]
    double_lo_slots: set[int]
    autoboxed_paths: set[TreePath]
    autoboxed_arg_indices: dict[TreePath, set[int]]

    def __getitem__(self, key: int):
        n = key / Memory.WORD_LEN
        assert n.is_integer()
        return self.slots[int(n)]

    def __len__(self):
        return len(self.slots) * Memory.WORD_LEN

    def try_get_slot(self, path: TreePath):
        return self.lookup_slots.get(path)

    def get_slot(self, path: TreePath):
        if slot := self.try_get_slot(path):
            return slot
        raise CompilerError(f"slot '{path}' not found")

    def get_tag_slot(self, path: TreePath):
        return self.get_slot(Memory.to_tag(path))

    def write_callee_tags(self, units: Iterable[BytecodeUnit]):
        for i, unit in enumerate(units):
            slot = self.get_slot(unit.path)
            self.slots[slot].value = i

    @staticmethod
    def from_inferrer_result(res: InferrerResult) -> Memory:
        """Построить карту памяти по результатам вывода типов.

        Проходит все переменные, константы, параметры функций и выделяет
        каждому уникальный слот. DOUBLE занимает 2 слота, STRING — длину + символы.
        """
        inferred = res.all_inferred
        autoboxed_paths = res.autoboxed_paths

        next_cell = Memory.INITIAL_NEXT_FREE_CELL()

        mem_decl: dict[TreePath, int] = {}
        lookup_slots: dict[TreePath, int] = {}
        lookup_args: dict[TreePath, list[int]] = {}
        lookup_captures_sources: dict[TreePath, list[int]] = {}
        lookup_captures_destinations: dict[TreePath, list[int]] = {}
        lookup_builtin_lambda_slots: dict[TreePath, list[int]] = {}
        double_lo_slots: set[int] = set()
        autoboxed_arg_indices: dict[TreePath, set[int]] = {}

        for inf in inferred:
            if isinstance(inf.qualname, BaseConstQualName):
                if isinstance(inf.qualname, StringConstQualName):
                    mem_decl[Memory.to_string_length(inf.qualname.path)] = next_cell
                    lookup_slots[Memory.to_string_length(inf.qualname.path)] = next_cell
                    next_cell += Memory.WORD_LEN
                    for i in range(len(inf.qualname.const)):
                        mem_decl[Memory.to_string_char(inf.qualname.path, i)] = next_cell
                        next_cell += Memory.WORD_LEN
                if isinstance(inf.qualname, DoubleConstQualName):
                    # Doubles need 2 consecutive slots: lo then hi
                    mem_decl[inf.qualname.path] = next_cell
                    double_lo_slots.add(next_cell)
                    next_cell += Memory.WORD_LEN
                    mem_decl[Memory.to_double_hi(inf.qualname.path)] = next_cell
                    lookup_slots[Memory.to_double_hi(inf.qualname.path)] = next_cell
                    next_cell += Memory.WORD_LEN
                else:
                    mem_decl[inf.qualname.path] = next_cell
                    next_cell += Memory.WORD_LEN

        seen_builtin_paths: set[str] = set()
        for inf in inferred:
            if isinstance(inf.qualname, BuiltinQualName):
                assert isinstance(inf.lang_type, FunctionLanguageType)

                path_key = str(inf.qualname.path)
                if path_key in seen_builtin_paths:
                    continue
                seen_builtin_paths.add(path_key)

                if not inf.qualname.symbol.is_atomic:
                    mem_decl[Memory.to_tag(inf.qualname.path)] = next_cell
                    lookup_slots[Memory.to_tag(inf.qualname.path)] = next_cell
                    next_cell += Memory.WORD_LEN
                    for i in range(len(inf.lang_type.arg_types)):
                        lookup_args.setdefault(inf.qualname.path, []).append(next_cell)
                        mem_decl[Memory.to_builtin_lambda_arg(inf.qualname.path, i)] = next_cell
                        lookup_slots[Memory.to_builtin_lambda_arg(inf.qualname.path, i)] = next_cell
                        if inf.lang_type.arg_types[i] == PrimitiveLanguageType.DOUBLE:
                            double_lo_slots.add(next_cell)
                        next_cell += Memory.WORD_LEN
                        # DOUBLE args need an adjacent hi slot
                        if inf.lang_type.arg_types[i] == PrimitiveLanguageType.DOUBLE:
                            hi_path = Memory.to_builtin_lambda_arg_hi(inf.qualname.path, i)
                            lookup_args[inf.qualname.path].append(next_cell)
                            mem_decl[hi_path] = next_cell
                            lookup_slots[hi_path] = next_cell
                            next_cell += Memory.WORD_LEN

        for inf in inferred:
            inf_token = inf.token
            if not isinstance(inf_token, VirtualToken):
                token_s_expr = inf_token.s_expr
                if isinstance(token_s_expr, SExprDefun):
                    mem_decl[Memory.to_tag(inf.qualname.path)] = next_cell
                    lookup_slots[Memory.to_tag(inf.qualname.path)] = next_cell
                    next_cell += Memory.WORD_LEN
                    assert isinstance(inf.lang_type, FunctionLanguageType)
                    for arg_idx, arg in enumerate(token_s_expr.args):
                        lookup_args.setdefault(inf.qualname.path, []).append(next_cell)
                        mem_decl[arg.qualname.path] = next_cell
                        if (
                            arg_idx < len(inf.lang_type.arg_types)
                            and inf.lang_type.arg_types[arg_idx] == PrimitiveLanguageType.DOUBLE
                        ):
                            double_lo_slots.add(next_cell)
                        next_cell += Memory.WORD_LEN
                        if (
                            arg_idx < len(inf.lang_type.arg_types)
                            and inf.lang_type.arg_types[arg_idx] == PrimitiveLanguageType.DOUBLE
                        ):
                            hi_path = Memory.to_double_hi(arg.qualname.path)
                            lookup_args[inf.qualname.path].append(next_cell)
                            mem_decl[hi_path] = next_cell
                            lookup_slots[hi_path] = next_cell
                            next_cell += Memory.WORD_LEN
                        # Track autoboxed arg indices
                        if arg.qualname.path in autoboxed_paths:
                            autoboxed_arg_indices.setdefault(inf.qualname.path, set()).add(arg_idx)

        for inf in inferred:
            inf_token = inf.token
            if not isinstance(inf_token, VirtualToken):
                token_s_expr = inf_token.s_expr
                if isinstance(token_s_expr, SExprLambda):
                    mem_decl[Memory.to_tag(inf.qualname.path)] = next_cell
                    lookup_slots[Memory.to_tag(inf.qualname.path)] = next_cell
                    next_cell += Memory.WORD_LEN
                    assert isinstance(inf.lang_type, FunctionLanguageType)
                    for arg_idx, arg in enumerate(token_s_expr.args):
                        lookup_args.setdefault(inf.qualname.path, []).append(next_cell)
                        mem_decl[arg.qualname.path] = next_cell
                        if (
                            arg_idx < len(inf.lang_type.arg_types)
                            and inf.lang_type.arg_types[arg_idx] == PrimitiveLanguageType.DOUBLE
                        ):
                            double_lo_slots.add(next_cell)
                        next_cell += Memory.WORD_LEN
                        if (
                            arg_idx < len(inf.lang_type.arg_types)
                            and inf.lang_type.arg_types[arg_idx] == PrimitiveLanguageType.DOUBLE
                        ):
                            hi_path = Memory.to_double_hi(arg.qualname.path)
                            lookup_args[inf.qualname.path].append(next_cell)
                            mem_decl[hi_path] = next_cell
                            lookup_slots[hi_path] = next_cell
                            next_cell += Memory.WORD_LEN
                        # Track autoboxed arg indices
                        if arg.qualname.path in autoboxed_paths:
                            autoboxed_arg_indices.setdefault(inf.qualname.path, set()).add(arg_idx)
                    for virtual_inf in inferred:
                        if (
                            isinstance(virtual_inf.qualname, ProjectionQualName)
                            and virtual_inf.qualname.projection_scope == inf.qualname.path
                        ):
                            mem_decl[virtual_inf.qualname.path] = next_cell
                            if virtual_inf.lang_type == PrimitiveLanguageType.DOUBLE:
                                double_lo_slots.add(next_cell)
                            next_cell += Memory.WORD_LEN
                            if virtual_inf.lang_type == PrimitiveLanguageType.DOUBLE:
                                hi_path = Memory.to_double_hi(virtual_inf.qualname.path)
                                mem_decl[hi_path] = next_cell
                                lookup_slots[hi_path] = next_cell
                                next_cell += Memory.WORD_LEN

        seen_lambda_paths: set[str] = set()
        for inf in inferred:
            if isinstance(inf.qualname, BuiltinQualName) and inf.qualname.symbol.emit_lambda:
                path_key = str(inf.qualname.path)
                if path_key in seen_lambda_paths:
                    continue
                seen_lambda_paths.add(path_key)
                lookup_builtin_lambda_slots[inf.qualname.path] = []
                for slot in inf.qualname.symbol.emit_lambda.slots:
                    mem_decl[Memory.to_builtin_lambda_slot(inf.qualname.path, slot)] = next_cell
                    lookup_slots[Memory.to_builtin_lambda_slot(inf.qualname.path, slot)] = next_cell
                    lookup_builtin_lambda_slots[inf.qualname.path].append(next_cell)
                    next_cell += Memory.WORD_LEN

        for inf in inferred:
            if isinstance(inf.qualname, UsageQualName):
                continue
            if isinstance(inf.qualname, BuiltinQualName) and inf.qualname.symbol.is_atomic:
                continue
            if inf.qualname.path not in mem_decl:
                mem_decl[inf.qualname.path] = next_cell
                next_cell += Memory.WORD_LEN

        mem = (
            [
                MemorySlot32(TreePathEntry("heap", False).as_entire_tree_path(), 0),
                MemorySlot32(TreePathEntry("k", False).as_entire_tree_path(), 0),
                MemorySlot32(TreePathEntry("PORT_IN", False).as_entire_tree_path(), 0),
                MemorySlot32(TreePathEntry("PORT_OUT", False).as_entire_tree_path(), 0),
                *(
                    MemorySlot32(
                        TreePathEntry(f"ARG_SLOT_{i + 1}", False).as_entire_tree_path(),
                        0,
                    )
                    for i in range(Memory.MAX_ARITY)
                ),
                MemorySlot32(TreePathEntry("INT_VECTOR_INPUT", False).as_entire_tree_path(), 0),
                MemorySlot32(
                    TreePathEntry(
                        "DEFAULT_INT_HANDLER_INPUT_NEXT_BUF_IDX", False
                    ).as_entire_tree_path(),
                    0,
                ),
            ]
            + [
                MemorySlot32(
                    TreePathEntry(
                        f"DEFAULT_INT_HANDLER_INPUT_BUF_CELL_{i:03}", False
                    ).as_entire_tree_path(),
                    0,
                )
                for i, _ in enumerate(Memory.default_int_handler_input_buf_slots())
            ]
            + [None] * len(mem_decl)
        )

        for q, index in mem_decl.items():
            mem[index // 4] = MemorySlot32(q, 0)

        mem_slots: list[MemorySlot32] = cast(list[MemorySlot32], mem)

        for inf in inferred:
            if isinstance(inf.qualname, UsageQualName):
                lookup_slots[inf.qualname.path] = next(
                    i * Memory.WORD_LEN
                    for i, m in enumerate(mem_slots)
                    if m.path == inf.qualname.definition_path
                )
            elif isinstance(inf.qualname, BuiltinQualName) and inf.qualname.symbol.is_atomic:
                continue
            else:
                lookup_slots[inf.qualname.path] = next(
                    i * Memory.WORD_LEN
                    for i, m in enumerate(mem_slots)
                    if m.path == inf.qualname.path
                )
            if isinstance(inf.qualname, ProjectionQualName):
                lookup_captures_sources.setdefault(inf.qualname.projection_scope, []).append(
                    next(
                        i * Memory.WORD_LEN
                        for i, m in enumerate(mem_slots)
                        if m.path == inf.qualname.definition_path
                    )
                )
                lookup_captures_destinations.setdefault(inf.qualname.projection_scope, []).append(
                    next(
                        i * Memory.WORD_LEN
                        for i, m in enumerate(mem_slots)
                        if m.path == inf.qualname.path
                    )
                )
                if inf.lang_type == PrimitiveLanguageType.DOUBLE:
                    hi_def_path = Memory.to_double_hi(inf.qualname.definition_path)
                    hi_proj_path = Memory.to_double_hi(inf.qualname.path)
                    lookup_captures_sources[inf.qualname.projection_scope].append(
                        next(
                            i * Memory.WORD_LEN
                            for i, m in enumerate(mem_slots)
                            if m.path == hi_def_path
                        )
                    )
                    lookup_captures_destinations[inf.qualname.projection_scope].append(
                        next(
                            i * Memory.WORD_LEN
                            for i, m in enumerate(mem_slots)
                            if m.path == hi_proj_path
                        )
                    )

        return Memory(
            mem_slots,
            lookup_slots,
            lookup_args,
            lookup_captures_sources,
            lookup_captures_destinations,
            lookup_builtin_lambda_slots,
            double_lo_slots,
            autoboxed_paths,
            autoboxed_arg_indices,
        )

    @staticmethod
    def to_tag(path: TreePath):
        return path.combine(TreePathEntry("{TAG}", False))

    @staticmethod
    def to_builtin_lambda_arg(path: TreePath, i: int):
        return path.combine(TreePathEntry(f"{{ARG_{(i + 1):02}}}", False))

    @staticmethod
    def to_builtin_lambda_arg_hi(path: TreePath, i: int):
        return path.combine(TreePathEntry(f"{{ARG_{(i + 1):02}_HI}}", False))

    @staticmethod
    def to_builtin_lambda_slot(path: TreePath, slot: str):
        return path.combine(TreePathEntry(f"{{{slot}}}", False))

    @staticmethod
    def to_double_hi(path: TreePath):
        return path.combine(TreePathEntry("{DOUBLE_HI}", False))

    @staticmethod
    def to_string_length(path: TreePath):
        return path.combine(TreePathEntry("{LENGTH}", False))

    @staticmethod
    def to_string_char(path: TreePath, i: int):
        return path.combine(TreePathEntry(f"{{CHAR_{(i + 1):03}}}", False))
