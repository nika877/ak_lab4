from dataclasses import dataclass
from typing import Callable, Sequence, assert_never

from lang.lang_type import FunctionLanguageType
from lang.parser.qualname import BaseConstQualName, BooleanConstQualName, BuiltinQualName, FloatConstQualName, IntegerConstQualName, ProjectionQualName, StringConstQualName, TreePath, TreePathEntry, UsageQualName, DefinitionQualName, GenericBuiltinQualName, QualName
from lang.parser.step_02_analyze_s_expr import SExprCall, SExprDefun, SExprFile, SExprIf, SExprLambda
from lang.parser.step_04_assign_qualnames import FinalToken, Token_Step_04, VirtualToken

from .bytecode import BC, BytecodeUnit, IncompleteJmpIndex, iter_bytecode
from .memory import Memory
from .inferrer import InferredQualName, InferrerResult, infer


@dataclass(slots=True)
class CompilationResultMeta:
    memory: Memory
    processed_units: list[BytecodeUnit]


@dataclass(slots=True)
class CompilationResult:
    bytecode: list[int]
    entry_point: int
    meta: CompilationResultMeta


@dataclass
class Compiler:
    UNIT_MAIN = TreePathEntry("main", True).as_entire_tree_path()
    UNIT_K_APPLY = TreePathEntry("k_apply", True).as_entire_tree_path()

    memory: Memory
    units_stack: list[BytecodeUnit]
    processed_units: list[BytecodeUnit]

    @property
    def current_unit(self):
        return self.units_stack[-1]

    @property
    def current_unit_len(self):
        return len(self.current_unit.bytecode)

    def extend_current_unit(self, bc: list[int]):
        self.current_unit.bytecode.extend(bc)

    def push_unit(self, path: TreePath):
        self.units_stack.append(BytecodeUnit(path))

    def pop_unit(self):
        return self.units_stack.pop()

    @staticmethod
    def compile(inferrer_result: InferrerResult):
        assert isinstance(inferrer_result.file_token.s_expr, SExprFile)

        memory = Memory.from_inferrer_result(inferrer_result)
        compiler = Compiler(
            memory=memory,
            units_stack=[BytecodeUnit(Compiler.UNIT_MAIN)],
            processed_units=[]
        )

        for inferred in inferrer_result.all_inferred:
            if isinstance(inferred.qualname, BuiltinQualName):
                if inferred.qualname.symbol.emit_lambda:
                    compiler.make_builtin_lambda(inferred)

        for st in inferrer_result.file_token.s_expr.body:
            compiler.compile_token(st)

        compiler.build_k_apply()

        main_unit = compiler.units_stack.pop()
        compiler.processed_units = compiler.processed_units + [main_unit]

        compiler.assign_consts(inferrer_result.all_inferred)

        heap_start = len(compiler.memory.slots) + sum(len(u.bytecode) for u in compiler.processed_units)
        compiler.memory.slots[Memory.HEAP].value = heap_start

        main_unit_index = compiler.find_unit_index(Compiler.UNIT_MAIN)
        main_start = len(compiler.memory.slots) + sum(
            len(u.bytecode) for u in compiler.processed_units[:main_unit_index]
        )

        compiler.complete_indicies()

        final_bytecode = [slot.value for slot in compiler.memory.slots]
        final_bytecode.extend([c for unit in compiler.processed_units for c in unit.bytecode])

        return CompilationResult(
            bytecode=final_bytecode,
            entry_point=main_start,
            meta=CompilationResultMeta(
                memory,
                compiler.processed_units
            )
        )

    def find_unit_index(self, path: TreePath):
        return next(i for i, u in enumerate(self.processed_units) if u.path == path)

    def build_k_apply(self):
        jmp_table_cond_indicies = []
        jmp_table_exit_indicies = []

        self.push_unit(Compiler.UNIT_K_APPLY)

        for i, u in enumerate(self.processed_units):
            jmp_table_cond_indicies.append(self.current_unit_len + 5)
            self.extend_current_unit([
                BC.LOAD_IND_MEM,
                Memory.K,
                BC.NE_IMM,
                i,
                BC.JMP_T,
                -1
            ])
            for arg_src, arg_dst in zip(Memory.arg_slots(), self.memory.lookup_args[u.path]):
                self.extend_current_unit([
                    BC.LOAD_MEM,
                    arg_src,
                    BC.STORE_MEM,
                    arg_dst,
                ])
            for dst in self.memory.lookup_captures_destinations.get(u.path, []):
                self.extend_current_unit([
                    BC.LOAD_MEM,
                    Memory.K,
                    BC.ADD_IMM,
                    1,
                    BC.STORE_MEM,
                    Memory.K,
                    BC.LOAD_IND_MEM,
                    Memory.K,
                    BC.STORE_MEM,
                    dst,
                ])
            self.current_unit.incomplete_indicies.append(IncompleteJmpIndex(
                self.current_unit_len + 1,
                u.path
            ))
            self.extend_current_unit([
                BC.JMP,
                -1
            ])
            self.current_unit.bytecode[jmp_table_cond_indicies.pop()] = self.current_unit_len

        for i in jmp_table_exit_indicies:
            self.current_unit.bytecode[i] = self.current_unit_len

        self.extend_current_unit([BC.LOAD_IMM, -2, BC.HALT])

        unit = self.pop_unit()
        self.processed_units.append(unit)

    def complete_indicies(self):
        offset = len(self.memory.slots)
        for unit in self.processed_units:
            for i, bc, _ in iter_bytecode(unit.bytecode):
                match bc:
                    case BC.JMP | BC.JMP_T:
                        unit.bytecode[i+1] += offset
            offset += len(unit.bytecode)

        for unit in self.processed_units:
            for entry in unit.incomplete_indicies:
                unit_index = next(
                    i for i, u in enumerate(self.processed_units) if u.path == entry.path
                )
                unit.bytecode[entry.i] = len(self.memory.slots) + sum(
                    len(u.bytecode) for u in self.processed_units[:unit_index]
                )

    def compile_token(self, token: FinalToken):
        if isinstance(token, VirtualToken):
            return
        if not token.s_expr:
            return

        match token.s_expr:
            case SExprIf():
                self.compile_if_expr(token, token.s_expr)
            case SExprDefun():
                self.compile_defun(token, token.s_expr)
            case SExprLambda():
                self.compile_lambda(token, token.s_expr)
            case SExprCall():
                self.compile_call(token, token.s_expr)
            case _:
                raise Exception(f"Invalid expr after cps-transformation: {token.source}")

    def compile_if_expr(self, token: Token_Step_04, if_expr: SExprIf[Token_Step_04]):
        self.compile_token(if_expr.cond)
        jmp_t_index = self.current_unit_len + 3
        self.extend_current_unit([
            BC.LOAD_MEM,
            self.memory.get_slot(if_expr.cond.qualname.path),
            BC.JMP_T,
            -1,
        ])
        self.compile_token(if_expr.branch_f)
        jmp_index = self.current_unit_len + 3
        self.extend_current_unit([
            BC.LOAD_MEM,
            self.memory.get_slot(if_expr.branch_f.qualname.path),
            BC.JMP,
            -1,
        ])
        self.current_unit.bytecode[jmp_t_index] = self.current_unit_len
        self.compile_token(if_expr.branch_t)
        self.current_unit.bytecode[jmp_index] = self.current_unit_len + 3
        self.extend_current_unit([
            BC.LOAD_MEM,
            self.memory.get_slot(if_expr.branch_t.qualname.path),
            BC.STORE_MEM,
            self.memory.get_slot(token.qualname.path)
        ])

    def compile_defun(self, token: Token_Step_04, defun: SExprDefun[Token_Step_04]):
        self.push_unit(token.qualname.path)
        self.compile_token(defun.body)
        unit = self.pop_unit()
        self.processed_units.append(unit)

    def compile_lambda(self, token: Token_Step_04, lamb: SExprLambda[Token_Step_04]):
        self.push_unit(token.qualname.path)
        self.compile_token(lamb.body)
        unit = self.pop_unit()
        self.processed_units.append(unit)
        self.extend_current_unit([
            BC.LOAD_MEM,
            Memory.HEAP,
            BC.STORE_MEM,
            self.memory.get_slot(token.qualname.path),
            BC.LOAD_MEM,
            self.memory.get_tag_slot(token.qualname.path),
            BC.STORE_IND_MEM,
            Memory.HEAP,
            BC.LOAD_MEM,
            Memory.HEAP,
            BC.ADD_IMM,
            1,
            BC.STORE_MEM,
            Memory.HEAP
        ])
        self.extend_current_unit([
            c
            for src in self.memory.lookup_captures_sources.get(token.qualname.path, [])
            for c in [
                BC.LOAD_MEM,
                src,
                BC.STORE_IND_MEM,
                Memory.HEAP,
                BC.LOAD_MEM,
                Memory.HEAP,
                BC.ADD_IMM,
                1,
                BC.STORE_MEM,
                Memory.HEAP
            ]
        ])

    def compile_call(self, token: Token_Step_04, call: SExprCall[Token_Step_04]):
        assert not isinstance(call.callee.qualname, GenericBuiltinQualName)

        self.compile_token(call.callee)
        for arg in call.args:
            self.compile_token(arg)

        if isinstance(call.callee.qualname, BuiltinQualName):
            assert call.callee.qualname.symbol.emit_inplace
            rt_slot = self.memory.get_slot(token.qualname.path)
            args_slots = [
                self.memory.get_slot(arg.qualname.path)
                for arg in call.args
            ]
            call.callee.qualname.symbol.emit_inplace(self.current_unit, rt_slot, *args_slots)
            return

        Compiler.emit_load_k(
            self.current_unit,
            self.memory.get_slot(call.callee.qualname.path)
        )

        Compiler.emit_load_k_args(
            self.current_unit,
            [
                self.memory.get_slot(arg.qualname.path)
                for arg in call.args
            ]
        )

        Compiler.emit_apply_k(self.current_unit)

    def make_builtin_lambda(self, inferred: InferredQualName):
        assert isinstance(inferred.lang_type, FunctionLanguageType)
        assert isinstance(inferred.qualname, BuiltinQualName)
        assert inferred.qualname.symbol.emit_lambda

        self.push_unit(inferred.qualname.path)

        slots = [
            self.memory.get_slot(Memory.to_builtin_lambda_arg(inferred.qualname.path, i))
            for i in range(len(inferred.lang_type.arg_types))
        ]
        args_slots = slots[:-1]
        k_slot = slots[-1]

        print(args_slots, k_slot)

        inferred.qualname.symbol.emit_lambda(
            self.current_unit,
            k_slot,
            *args_slots
        )

        unit = self.pop_unit()
        self.processed_units.append(unit)


    def assign_consts(self, inferred_qualnames: Sequence[InferredQualName]):
        for inferred in inferred_qualnames:
            if isinstance(inferred.token, VirtualToken):
                continue

            if isinstance(inferred.qualname, (
                ProjectionQualName,
                UsageQualName,
            )):
                continue

            if isinstance(inferred.qualname, BuiltinQualName):
                print(f"Assigning builtin: {inferred.qualname.path}")
                if inferred.qualname.symbol.emit_lambda:
                    tag_slot = self.memory.get_tag_slot(inferred.qualname.path)
                    self.memory.slots[tag_slot].value = self.find_unit_index(inferred.qualname.path)
                    slot = self.memory.get_slot(inferred.qualname.path)
                    self.memory.slots[slot].value = tag_slot

            elif isinstance(inferred.qualname, IntegerConstQualName):
                slot = self.memory.get_slot(inferred.qualname.path)
                self.memory.slots[slot].value = inferred.qualname.const
            elif isinstance(inferred.qualname, FloatConstQualName):
                slot = self.memory.get_slot(inferred.qualname.path)
                #self.memory.slots[slot].value = inferred.qualname.const
            elif isinstance(inferred.qualname, BooleanConstQualName):
                slot = self.memory.get_slot(inferred.qualname.path)
                self.memory.slots[slot].value = [0, 1][inferred.qualname.const]
            elif isinstance(inferred.qualname, StringConstQualName):
                slot = self.memory.get_slot(inferred.qualname.path)
                #self.memory.slots[slot].value = inferred.qualname.const
            elif isinstance(inferred.qualname, DefinitionQualName):
                if isinstance(inferred.token.s_expr, (SExprDefun, SExprLambda)):
                    tag_slot = self.memory.get_tag_slot(inferred.qualname.path)
                    self.memory.slots[tag_slot].value = self.find_unit_index(inferred.qualname.path)
                    slot = self.memory.get_slot(inferred.qualname.path)
                    self.memory.slots[slot].value = tag_slot
            else:
                assert_never(inferred.qualname)

    @staticmethod
    def emit_load_k(unit: BytecodeUnit, k: int):
        unit.bytecode.extend([
            BC.LOAD_MEM,
            k,
            BC.STORE_MEM,
            Memory.K,
        ])

    @staticmethod
    def emit_load_k_args(unit: BytecodeUnit, args: Sequence[int]):
        unit.bytecode.extend([
            c
            for arg_scr, arg_dst in zip(args, Memory.arg_slots())
            for c in [
                BC.LOAD_MEM,
                arg_scr,
                BC.STORE_MEM,
                arg_dst,
            ]
        ])

    @staticmethod
    def emit_write_k_args_inplace(
        unit: BytecodeUnit,
        args_builder: Sequence[Sequence[int]]
    ):
        unit.bytecode.extend([
            c
            for arg_builder in args_builder
            for c in [
                *arg_builder,
                BC.STORE_MEM,
                Memory.K
            ]
        ])

    @staticmethod
    def emit_apply_k(unit: BytecodeUnit):
        unit.bytecode.extend([
            BC.JMP,
            -1
        ])
        unit.incomplete_indicies.append(IncompleteJmpIndex(
            len(unit.bytecode) - 1,
            Compiler.UNIT_K_APPLY
        ))
