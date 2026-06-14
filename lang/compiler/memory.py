from dataclasses import dataclass
from typing import Callable, Iterable, Self, cast

from lang.lang_type import FunctionLanguageType
from lang.parser import ParserResult
from lang.parser.step_02_analyze_s_expr import SExprDefun, SExprLambda
from lang.parser.step_04_assign_qualnames import VirtualToken

from .bytecode import BytecodeUnit
from lang.parser.qualname import BaseConstQualName, BuiltinQualName, DefinitionQualName, ProjectionQualName, TreePath, TreePathEntry, UsageQualName, QualName

from .inferrer import InferredQualName, InferrerResult


@dataclass
class MemorySlot:
    path: TreePath
    value: int


@dataclass
class LookupCaptureEntry:
    variable_path: TreePath
    slot: int


@dataclass
class Memory:
    HEAP = 0
    K = 1
    ARG_SLOT_1 = 2
    ARG_SLOT_2 = 3
    ARG_SLOT_3 = 4
    ARG_SLOT_4 = 5
    ARG_SLOT_5 = 6
    ARG_SLOT_6 = 7
    ARG_SLOT_7 = 8
    ARG_SLOT_8 = 9

    slots: list[MemorySlot]
    lookup_slots: dict[TreePath, int]
    lookup_args: dict[TreePath, list[int]]
    lookup_captures_sources: dict[TreePath, list[int]]
    lookup_captures_destinations: dict[TreePath, list[int]]

    def try_get_slot(self, path: TreePath):
        return self.lookup_slots.get(path)

    def get_slot(self, path: TreePath):
        if slot := self.try_get_slot(path):
            return slot
        raise Exception(f"slot '{path}' not found")

    def get_tag_slot(self, path: TreePath):
        return self.get_slot(Memory.to_tag(path))

    def write_callee_tags(self, units: Iterable[BytecodeUnit]):
        for i, unit in enumerate(units):
            slot = self.get_slot(unit.path)
            self.slots[slot].value = i

    @staticmethod
    def from_inferrer_result(res: InferrerResult) -> Memory:
        inferred = res.all_inferred

        next_cell = Memory.ARG_SLOT_8 + 1

        mem_decl: dict[TreePath, int] = {}
        lookup_slots: dict[TreePath, int] = {}
        lookup_args: dict[TreePath, list[int]] = {}
        lookup_captures_sources: dict[TreePath, list[int]] = {}
        lookup_captures_destinations: dict[TreePath, list[int]] = {}

        for inf in inferred:
            if isinstance(inf.qualname, BaseConstQualName):
                mem_decl[inf.qualname.path] = next_cell
                next_cell += 1

        for inf in inferred:
            if isinstance(inf.qualname, BuiltinQualName):
                assert isinstance(inf.lang_type, FunctionLanguageType)

                if not inf.qualname.symbol.is_inplace:
                    mem_decl[Memory.to_tag(inf.qualname.path)] = next_cell
                    lookup_slots[Memory.to_tag(inf.qualname.path)] = next_cell
                    next_cell += 1
                    for i in range(len(inf.lang_type.arg_types)):
                        lookup_args.setdefault(inf.qualname.path, []).append(next_cell)
                        mem_decl[Memory.to_builtin_lambda_arg(inf.qualname.path, i)] = next_cell
                        lookup_slots[Memory.to_builtin_lambda_arg(inf.qualname.path, i)] = next_cell
                        next_cell += 1

        for inf in inferred:
            if not isinstance(inf.token, VirtualToken):
                if isinstance(inf.token.s_expr, SExprDefun):
                    mem_decl[Memory.to_tag(inf.qualname.path)] = next_cell
                    lookup_slots[Memory.to_tag(inf.qualname.path)] = next_cell
                    next_cell += 1
                    for arg in inf.token.s_expr.args:
                        lookup_args.setdefault(inf.qualname.path, []).append(next_cell)
                        mem_decl[arg.qualname.path] = next_cell
                        next_cell += 1

        for inf in inferred:
            if not isinstance(inf.token, VirtualToken):
                if isinstance(inf.token.s_expr, SExprLambda):
                    mem_decl[Memory.to_tag(inf.qualname.path)] = next_cell
                    lookup_slots[Memory.to_tag(inf.qualname.path)] = next_cell
                    next_cell += 1
                    for arg in inf.token.s_expr.args:
                        lookup_args.setdefault(inf.qualname.path, []).append(next_cell)
                        mem_decl[arg.qualname.path] = next_cell
                        next_cell += 1
                    for virtual_inf in inferred:
                        if isinstance(virtual_inf.qualname, ProjectionQualName):
                            if virtual_inf.qualname.projection_scope == inf.qualname.path:
                                mem_decl[virtual_inf.qualname.path] = next_cell
                                next_cell += 1

        for inf in inferred:
            if isinstance(inf.qualname, UsageQualName):
                continue
            if isinstance(inf.qualname, BuiltinQualName) and inf.qualname.symbol.is_inplace:
                continue
            if inf.qualname.path not in mem_decl:
                mem_decl[inf.qualname.path] = next_cell
                next_cell += 1

        mem = [
            MemorySlot(TreePathEntry("heap", False).as_entire_tree_path(), 0),
            MemorySlot(TreePathEntry("k", False).as_entire_tree_path(), 0),
            MemorySlot(TreePathEntry("ARG_SLOT_1", False).as_entire_tree_path(), 0),
            MemorySlot(TreePathEntry("ARG_SLOT_2", False).as_entire_tree_path(), 0),
            MemorySlot(TreePathEntry("ARG_SLOT_3", False).as_entire_tree_path(), 0),
            MemorySlot(TreePathEntry("ARG_SLOT_4", False).as_entire_tree_path(), 0),
            MemorySlot(TreePathEntry("ARG_SLOT_5", False).as_entire_tree_path(), 0),
            MemorySlot(TreePathEntry("ARG_SLOT_6", False).as_entire_tree_path(), 0),
            MemorySlot(TreePathEntry("ARG_SLOT_7", False).as_entire_tree_path(), 0),
            MemorySlot(TreePathEntry("ARG_SLOT_8", False).as_entire_tree_path(), 0),
        ] + [None] * len(mem_decl)

        for q, index in mem_decl.items():
            mem[index] = MemorySlot(q, 0)

        mem = cast(list[MemorySlot], mem)

        for slot in mem:
            print(f"{slot.path}")

        for inf in inferred:
            if isinstance(inf.qualname, UsageQualName):
                lookup_slots[inf.qualname.path] = next(
                    i for i, m in enumerate(mem) if m.path == inf.qualname.definition_path
                )
            elif isinstance(inf.qualname, BuiltinQualName) and inf.qualname.symbol.is_inplace:
                continue
            else:
                lookup_slots[inf.qualname.path] = next(
                    i for i, m in enumerate(mem) if m.path == inf.qualname.path
                )
            if isinstance(inf.qualname, ProjectionQualName):
                lookup_captures_sources.setdefault(inf.qualname.projection_scope, [])\
                    .append(next(
                        i for i, m in enumerate(mem) if m.path == inf.qualname.definition_path
                    ))
                lookup_captures_destinations.setdefault(inf.qualname.projection_scope, [])\
                    .append(next(
                        i for i, m in enumerate(mem) if m.path == inf.qualname.path
                    ))

        return Memory(
            mem,
            lookup_slots,
            lookup_args,
            lookup_captures_sources,
            lookup_captures_destinations
        )

    @staticmethod
    def arg_slots():
        yield Memory.ARG_SLOT_1
        yield Memory.ARG_SLOT_2
        yield Memory.ARG_SLOT_3
        yield Memory.ARG_SLOT_4
        yield Memory.ARG_SLOT_5
        yield Memory.ARG_SLOT_6
        yield Memory.ARG_SLOT_7
        yield Memory.ARG_SLOT_8
        raise Exception("Maximum arity of 8 was superseded")

    @staticmethod
    def to_tag(path: TreePath):
        return path.combine(TreePathEntry("{TAG}", False))

    @staticmethod
    def to_builtin_lambda_arg(path: TreePath, i: int):
        return path.combine(TreePathEntry(f"{{ARG_{(i+1):02}}}", False))
