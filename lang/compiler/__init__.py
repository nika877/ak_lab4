import struct
from collections.abc import Sequence
from dataclasses import dataclass

from lang.exceptions import CompilerError
from lang.lang_type import FunctionLanguageType
from lang.parser.qualname import (
    BooleanConstQualName,
    BuiltinQualName,
    DefinitionQualName,
    DoubleConstQualName,
    FloatConstQualName,
    GenericBuiltinQualName,
    IntegerConstQualName,
    ProjectionQualName,
    StringConstQualName,
    TreePath,
    TreePathEntry,
    UsageQualName,
)
from lang.parser.qualname_assign import FinalToken, QualifiedToken, VirtualToken
from lang.parser.s_expr import (
    SExprCall,
    SExprDefun,
    SExprFile,
    SExprIf,
    SExprLambda,
    SExprProgn,
    SExprSetq,
    SExprWhile,
)
from lang.parser.token_storage import TokenView

from .bytecode import BC, BytecodeUnit, IncompleteJmpIndex, iter_bytecode
from .inferrer import InferredQualName, InferrerResult
from .memory import Memory

"""Генератор байткода: обход CPS-дерева → машинные команды.

Главный класс - Compiler. Он компилирует каждую конструкцию Lisp:
  if → JMP_T / JMP
  while → цикл с JMP назад
  setq → STORE_MEM / STORE_IND_MEM (для мутируемых)
  вызов функции → загрузка k, аргументов, переход в k_apply
"""


@dataclass(slots=True)
class CompilationResultMeta:
    """Метаданные компиляции: карта памяти и список фрагментов кода."""

    memory: Memory
    processed_units: list[BytecodeUnit]


@dataclass(slots=True)
class CompilationResult:
    """Итог компиляции: байты, точка входа и метаданные."""

    bytecode: bytes
    entry_point: int
    meta: CompilationResultMeta


@dataclass
class Compiler:
    """Компилятор: превращает типизированное CPS-дерево в байткод.

    Специальные фрагменты:
      UNIT_MAIN — точка входа программы
      UNIT_K_APPLY — диспетчер вызовов (по тегу функции выбирает код)
      UNIT_DEFAULT_INT_HANDLER_INPUT — обработчик прерывания ввода
    """

    UNIT_MAIN = TreePathEntry("main", True).as_entire_tree_path()
    UNIT_K_APPLY = TreePathEntry("k_apply", True).as_entire_tree_path()
    UNIT_DEFAULT_INT_HANDLER_INPUT = TreePathEntry(
        "default_interrupt_handler_input", True
    ).as_entire_tree_path()

    memory: Memory
    units_stack: list[BytecodeUnit]
    processed_units: list[BytecodeUnit]
    autoboxed_paths: set[TreePath]

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
        """Главная точка компиляции: типизированное дерево → байткод."""
        file_token = inferrer_result.file_token
        file_s_expr = file_token.s_expr
        assert isinstance(file_s_expr, SExprFile)

        memory = Memory.from_inferrer_result(inferrer_result)
        compiler = Compiler(
            memory=memory,
            units_stack=[BytecodeUnit(Compiler.UNIT_MAIN)],
            processed_units=[],
            autoboxed_paths=inferrer_result.autoboxed_paths,
        )

        for inferred in inferrer_result.all_inferred:
            if (
                isinstance(inferred.qualname, BuiltinQualName)
                and inferred.qualname.symbol.emit_lambda
            ):
                compiler.make_builtin_lambda(inferred)

        for st in file_s_expr.body:
            compiler.compile_token(st)

        compiler.build_k_apply()
        compiler.build_default_int_handler_input()

        main_unit = compiler.units_stack.pop()
        compiler.processed_units = compiler.processed_units + [main_unit]

        compiler.assign_consts(inferrer_result.all_inferred)

        heap_start = (
            len(compiler.memory.slots) + sum(len(u.bytecode) for u in compiler.processed_units)
        ) * Memory.WORD_LEN
        compiler.memory[Memory.HEAP].value = heap_start

        main_unit_index = compiler.find_unit_index(Compiler.UNIT_MAIN)
        main_start = (
            len(compiler.memory.slots)
            + sum(len(u.bytecode) for u in compiler.processed_units[:main_unit_index])
        ) * Memory.WORD_LEN

        compiler.complete_indicies()

        final_bytecode = [
            v for slot in compiler.memory.slots for v in struct.pack("<i", slot.value.value)
        ]
        final_bytecode.extend(
            [
                v
                for unit in compiler.processed_units
                for c in unit.bytecode
                for v in struct.pack("<i", c)
            ]
        )

        bytecode_bytes = bytes(final_bytecode)

        return CompilationResult(
            bytecode=bytecode_bytes,
            entry_point=main_start,
            meta=CompilationResultMeta(memory, compiler.processed_units),
        )

    def find_unit_index(self, path: TreePath):
        return next(i for i, u in enumerate(self.processed_units) if u.path == path)

    def build_k_apply(self):
        """Собрать диспетчер вызовов k_apply.

        При вызове функции в K кладётся «продолжение», в ARG_SLOT — аргументы.
        k_apply сравнивает тег функции и прыгает в нужный фрагмент кода.
        """
        jmp_table_cond_indicies = []
        jmp_table_exit_indicies = []

        self.push_unit(Compiler.UNIT_K_APPLY)

        for i, u in enumerate(self.processed_units):
            jmp_table_cond_indicies.append(self.current_unit_len + 5)
            self.extend_current_unit([BC.LOAD_IND_MEM, Memory.K, BC.NE_IMM, i, BC.JMP_T, -1])
            autoboxed_indices = self.memory.autoboxed_arg_indices.get(u.path, set())
            for arg_idx, (arg_src, arg_dst) in enumerate(
                zip(Memory.arg_slots(), self.memory.lookup_args[u.path], strict=False)
            ):
                if arg_idx in autoboxed_indices:
                    # Autoboxed param: allocate heap cell, store value there
                    self.extend_current_unit(
                        [
                            BC.LOAD_MEM,
                            Memory.HEAP,
                            BC.STORE_MEM,
                            arg_dst,
                            BC.LOAD_MEM,
                            arg_src,
                            BC.STORE_IND_MEM,
                            arg_dst,
                            BC.LOAD_MEM,
                            Memory.HEAP,
                            BC.ADD_IMM,
                            Memory.WORD_LEN,
                            BC.STORE_MEM,
                            Memory.HEAP,
                        ]
                    )
                else:
                    self.extend_current_unit(
                        [
                            BC.LOAD_MEM,
                            arg_src,
                            BC.STORE_MEM,
                            arg_dst,
                        ]
                    )
            for dst in self.memory.lookup_captures_destinations.get(u.path, []):
                self.extend_current_unit(
                    [
                        BC.LOAD_MEM,
                        Memory.K,
                        BC.ADD_IMM,
                        Memory.WORD_LEN,
                        BC.STORE_MEM,
                        Memory.K,
                        BC.LOAD_IND_MEM,
                        Memory.K,
                        BC.STORE_MEM,
                        dst,
                    ]
                )
            self.current_unit.incomplete_indicies.append(
                IncompleteJmpIndex(self.current_unit_len + 1, u.path)
            )
            self.extend_current_unit([BC.JMP, -1])
            self.current_unit.bytecode[jmp_table_cond_indicies.pop()] = (
                self.current_unit_len * Memory.WORD_LEN
            )

        for i in jmp_table_exit_indicies:
            self.current_unit.bytecode[i] = self.current_unit_len * Memory.WORD_LEN

        self.extend_current_unit([BC.LOAD_IMM, -2, BC.HALT])

        unit = self.pop_unit()
        self.processed_units.append(unit)

    def build_default_int_handler_input(self):
        """Обработчик прерывания ввода: читает символ из PORT_IN в буфер."""
        self.push_unit(Compiler.UNIT_DEFAULT_INT_HANDLER_INPUT)

        self.extend_current_unit(
            [
                BC.LOAD_MEM,
                Memory.PORT_IN,
                BC.STORE_IND_MEM,
                Memory.DEFAULT_INT_HANDLER_INPUT_NEXT_BUF_IDX,
                BC.LOAD_MEM,
                Memory.DEFAULT_INT_HANDLER_INPUT_NEXT_BUF_IDX,
                BC.ADD_IMM,
                Memory.WORD_LEN,
                BC.STORE_MEM,
                Memory.DEFAULT_INT_HANDLER_INPUT_NEXT_BUF_IDX,
                BC.IRET,
            ]
        )

        unit = self.pop_unit()
        self.processed_units.append(unit)

    def complete_indicies(self):
        offset = len(self.memory)
        for unit in self.processed_units:
            for i, bc, _ in iter_bytecode(unit.bytecode):
                match bc:
                    case BC.JMP | BC.JMP_T:
                        unit.bytecode[i + 1] += offset
            offset += len(unit.bytecode) * Memory.WORD_LEN

        for unit in self.processed_units:
            for entry in unit.incomplete_indicies:
                unit_index = next(
                    i for i, u in enumerate(self.processed_units) if u.path == entry.path
                )
                unit.bytecode[entry.i] = (
                    len(self.memory.slots)
                    + sum(len(u.bytecode) for u in self.processed_units[:unit_index])
                ) * Memory.WORD_LEN

    def _is_autoboxed(self, qualname) -> bool:
        """Нужна ли косвенная адресация (переменная в куче из-за setq в замыкании)."""
        if isinstance(qualname, UsageQualName):
            return qualname.definition_path in self.autoboxed_paths
        if isinstance(qualname, DefinitionQualName):
            return qualname.tree_path in self.autoboxed_paths
        if isinstance(qualname, ProjectionQualName):
            return qualname.definition_path in self.autoboxed_paths
        return False

    def _load_slot(self, qualname, slot: int):
        if self._is_autoboxed(qualname):
            self.extend_current_unit([BC.LOAD_IND_MEM, slot])
        else:
            self.extend_current_unit([BC.LOAD_MEM, slot])

    def compile_token(self, token: FinalToken):
        if isinstance(token, VirtualToken):
            return
        s_expr = token.s_expr
        if not s_expr:
            return

        match s_expr:
            case SExprIf():
                self.compile_if_expr(token, s_expr)
            case SExprDefun():
                self.compile_defun(token, s_expr)
            case SExprLambda():
                self.compile_lambda(token, s_expr)
            case SExprCall():
                self.compile_call(token, s_expr)
            case SExprSetq():
                self.compile_setq(token, s_expr)
            case SExprWhile():
                self.compile_while(token, s_expr)
            case SExprProgn():
                self.compile_progn(token, s_expr)
            case _:
                raise CompilerError(f"Invalid expr after cps-transformation: {token.source}")

    def compile_if_expr(
        self, token: TokenView[QualifiedToken], if_expr: SExprIf[TokenView[QualifiedToken]]
    ):
        """Компиляция (if cond t f): ветвление через JMP_T и JMP."""
        self.compile_token(if_expr.cond)
        cond_slot = self.memory.get_slot(if_expr.cond.qualname.path)
        cond_load = BC.LOAD_IND_MEM if self._is_autoboxed(if_expr.cond.qualname) else BC.LOAD_MEM
        jmp_t_index = self.current_unit_len + 3
        self.extend_current_unit(
            [
                cond_load,
                cond_slot,
                BC.JMP_T,
                -1,
            ]
        )
        self.compile_token(if_expr.branch_f)
        branch_f_slot = self.memory.get_slot(if_expr.branch_f.qualname.path)
        branch_f_load = (
            BC.LOAD_IND_MEM if self._is_autoboxed(if_expr.branch_f.qualname) else BC.LOAD_MEM
        )
        jmp_index = self.current_unit_len + 3
        self.extend_current_unit(
            [
                branch_f_load,
                branch_f_slot,
                BC.JMP,
                -1,
            ]
        )
        self.current_unit.bytecode[jmp_t_index] = self.current_unit_len * Memory.WORD_LEN
        self.compile_token(if_expr.branch_t)
        branch_t_slot = self.memory.get_slot(if_expr.branch_t.qualname.path)
        branch_t_load = (
            BC.LOAD_IND_MEM if self._is_autoboxed(if_expr.branch_t.qualname) else BC.LOAD_MEM
        )
        self.current_unit.bytecode[jmp_index] = (self.current_unit_len + 4) * Memory.WORD_LEN
        self.extend_current_unit(
            [
                branch_t_load,
                branch_t_slot,
                BC.STORE_MEM,
                self.memory.get_slot(token.qualname.path),
            ]
        )

    def compile_defun(
        self, token: TokenView[QualifiedToken], defun: SExprDefun[TokenView[QualifiedToken]]
    ):
        self.push_unit(token.qualname.path)
        self.compile_token(defun.body)
        unit = self.pop_unit()
        self.processed_units.append(unit)

    def compile_lambda(
        self, token: TokenView[QualifiedToken], lamb: SExprLambda[TokenView[QualifiedToken]]
    ):
        self.push_unit(token.qualname.path)
        self.compile_token(lamb.body)
        unit = self.pop_unit()
        self.processed_units.append(unit)
        self.extend_current_unit(
            [
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
                Memory.WORD_LEN,
                BC.STORE_MEM,
                Memory.HEAP,
            ]
        )
        self.extend_current_unit(
            [
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
                    Memory.WORD_LEN,
                    BC.STORE_MEM,
                    Memory.HEAP,
                ]
            ]
        )

    def compile_call(
        self, token: TokenView[QualifiedToken], call: SExprCall[TokenView[QualifiedToken]]
    ):
        assert not isinstance(call.callee.qualname, GenericBuiltinQualName)

        self.compile_token(call.callee)
        for arg in call.args:
            self.compile_token(arg)

        if (
            isinstance(call.callee.qualname, BuiltinQualName)
            and call.callee.qualname.symbol.is_atomic
        ):
            assert call.callee.qualname.symbol.emit_inplace
            rt_slot = self.memory.get_slot(token.qualname.path)
            args_slots = self._expand_double_args_autobox(call.args)
            call.callee.qualname.symbol.emit_inplace(self.current_unit, rt_slot, *args_slots)
            return

        Compiler.emit_load_k(self.current_unit, self.memory.get_slot(call.callee.qualname.path))

        self._emit_load_k_args_autobox(call.args)

        Compiler.emit_apply_k(self.current_unit)

    def compile_setq(
        self, token: TokenView[QualifiedToken], setq: SExprSetq[TokenView[QualifiedToken]]
    ):
        self.compile_token(setq.value)

        value_slot = self.memory.get_slot(setq.value.qualname.path)
        target_slot = self.memory.get_slot(setq.target.qualname.path)

        # Load value (possibly through indirection if autoboxed)
        self._load_slot(setq.value.qualname, value_slot)

        # Store to target (through indirection if autoboxed)
        if self._is_autoboxed(setq.target.qualname):
            self.extend_current_unit([BC.STORE_IND_MEM, target_slot])
        else:
            self.extend_current_unit([BC.STORE_MEM, target_slot])

        # Result is VOID
        result_slot = self.memory.get_slot(token.qualname.path)
        self.extend_current_unit(
            [
                BC.LOAD_IMM,
                0,
                BC.STORE_MEM,
                result_slot,
            ]
        )

    def compile_while(
        self, token: TokenView[QualifiedToken], while_expr: SExprWhile[TokenView[QualifiedToken]]
    ):
        """Компиляция (while cond body): цикл с проверкой условия в начале."""
        while_start_offset = self.current_unit_len * Memory.WORD_LEN

        # Compile condition
        self.compile_token(while_expr.cond)

        # Load condition result and branch
        cond_slot = self.memory.get_slot(while_expr.cond.qualname.path)
        jmp_t_idx = self.current_unit_len + 3
        self.extend_current_unit(
            [
                BC.LOAD_MEM,
                cond_slot,
                BC.JMP_T,
                -1,
            ]
        )

        # False: jump to end
        jmp_end_idx = self.current_unit_len + 1
        self.extend_current_unit([BC.JMP, -1])

        # True branch: compile body
        self.current_unit.bytecode[jmp_t_idx] = self.current_unit_len * Memory.WORD_LEN
        self.compile_token(while_expr.body)

        # Jump back to condition
        self.extend_current_unit([BC.JMP, while_start_offset])

        # End
        self.current_unit.bytecode[jmp_end_idx] = self.current_unit_len * Memory.WORD_LEN

        # Result is VOID
        result_slot = self.memory.get_slot(token.qualname.path)
        self.extend_current_unit(
            [
                BC.LOAD_IMM,
                0,
                BC.STORE_MEM,
                result_slot,
            ]
        )

    def compile_progn(
        self, token: TokenView[QualifiedToken], progn: SExprProgn[TokenView[QualifiedToken]]
    ):
        for st in progn.body:
            self.compile_token(st)
        if progn.body:
            last_slot = self.memory.get_slot(progn.body[-1].qualname.path)
            result_slot = self.memory.get_slot(token.qualname.path)
            self.extend_current_unit(
                [
                    BC.LOAD_MEM,
                    last_slot,
                    BC.STORE_MEM,
                    result_slot,
                ]
            )

    def _expand_double_args(self, args: Sequence[TokenView[QualifiedToken]]) -> list[int]:
        """Expand DOUBLE args into lo+hi physical slot pairs."""
        expanded: list[int] = []
        for arg in args:
            slot = self.memory.get_slot(arg.qualname.path)
            expanded.append(slot)
            if slot in self.memory.double_lo_slots:
                expanded.append(slot + Memory.WORD_LEN)
        return expanded

    def _expand_double_args_autobox(self, args: Sequence[TokenView[QualifiedToken]]) -> list[int]:
        """Expand DOUBLE args, pre-dereferencing autoboxed args into ARG_SLOTs as temp."""
        expanded: list[int] = []
        temp_iter = Memory.arg_slots()
        for arg in args:
            slot = self.memory.get_slot(arg.qualname.path)
            if self._is_autoboxed(arg.qualname):
                temp = next(temp_iter)
                self.extend_current_unit(
                    [
                        BC.LOAD_IND_MEM,
                        slot,
                        BC.STORE_MEM,
                        temp,
                    ]
                )
                expanded.append(temp)
            else:
                expanded.append(slot)
                if slot in self.memory.double_lo_slots:
                    expanded.append(slot + Memory.WORD_LEN)
        return expanded

    def _emit_load_k_args_autobox(self, args: Sequence[TokenView[QualifiedToken]]):
        """Load args into ARG_SLOTs, using LOAD_IND_MEM for autoboxed args."""
        arg_slot_gen = Memory.arg_slots()
        for arg in args:
            arg_dst = next(arg_slot_gen)
            slot = self.memory.get_slot(arg.qualname.path)
            if self._is_autoboxed(arg.qualname):
                self.extend_current_unit(
                    [
                        BC.LOAD_IND_MEM,
                        slot,
                        BC.STORE_MEM,
                        arg_dst,
                    ]
                )
            else:
                self.extend_current_unit(
                    [
                        BC.LOAD_MEM,
                        slot,
                        BC.STORE_MEM,
                        arg_dst,
                    ]
                )
                if slot in self.memory.double_lo_slots:
                    hi_dst = next(arg_slot_gen)
                    self.extend_current_unit(
                        [
                            BC.LOAD_MEM,
                            slot + Memory.WORD_LEN,
                            BC.STORE_MEM,
                            hi_dst,
                        ]
                    )

    def make_builtin_lambda(self, inferred: InferredQualName):
        assert isinstance(inferred.lang_type, FunctionLanguageType)
        assert isinstance(inferred.qualname, BuiltinQualName)
        assert inferred.qualname.symbol.emit_lambda

        self.push_unit(inferred.qualname.path)

        from lang.lang_type import PrimitiveLanguageType

        physical_slots = []
        for i, arg_type in enumerate(inferred.lang_type.arg_types):
            lo_slot = self.memory.get_slot(Memory.to_builtin_lambda_arg(inferred.qualname.path, i))
            physical_slots.append(lo_slot)
            if arg_type == PrimitiveLanguageType.DOUBLE:
                hi_slot = self.memory.get_slot(
                    Memory.to_builtin_lambda_arg_hi(inferred.qualname.path, i)
                )
                physical_slots.append(hi_slot)

        args_slots = physical_slots[:-1]
        k_slot = physical_slots[-1]

        inferred.qualname.symbol.emit_lambda.bytecode_emitter(
            self.current_unit,
            self.memory.lookup_builtin_lambda_slots[inferred.qualname.path],
            k_slot,
            *args_slots,
        )

        unit = self.pop_unit()
        self.processed_units.append(unit)

    def assign_consts(self, inferred_qualnames: Sequence[InferredQualName]):
        self.memory[Memory.DEFAULT_INT_HANDLER_INPUT_NEXT_BUF_IDX].value = next(
            Memory.default_int_handler_input_buf_slots()
        )

        if s := self.memory.try_get_slot(
            Memory.to_builtin_lambda_slot(
                TreePathEntry.for_builtin("input<string>").as_entire_tree_path(),
                "NEXT_BUF_PTR",
            )
        ):
            self.memory[s].value = next(Memory.default_int_handler_input_buf_slots())

        default_int_handler_idx = next(
            i
            for i, u in enumerate(self.processed_units)
            if u.path == Compiler.UNIT_DEFAULT_INT_HANDLER_INPUT
        )
        self.memory[Memory.INT_VECTOR_INPUT].value = (
            len(self.memory.slots)
            + sum(len(u.bytecode) for u in self.processed_units[:default_int_handler_idx])
        ) * Memory.WORD_LEN

        for inferred in inferred_qualnames:
            if isinstance(inferred.token, VirtualToken):
                continue

            if isinstance(
                inferred.qualname,
                (
                    ProjectionQualName,
                    UsageQualName,
                ),
            ):
                continue

            if isinstance(inferred.qualname, BuiltinQualName):
                if inferred.qualname.symbol.emit_lambda:
                    tag_slot = self.memory.get_tag_slot(inferred.qualname.path)
                    self.memory[tag_slot].value = self.find_unit_index(inferred.qualname.path)
                    slot = self.memory.get_slot(inferred.qualname.path)
                    self.memory[slot].value = tag_slot

            elif isinstance(inferred.qualname, (IntegerConstQualName, FloatConstQualName)):
                slot = self.memory.get_slot(inferred.qualname.path)
                self.memory[slot].value = inferred.qualname.const
            elif isinstance(inferred.qualname, DoubleConstQualName):
                lo_slot = self.memory.get_slot(inferred.qualname.path)
                hi_slot = self.memory.get_slot(Memory.to_double_hi(inferred.qualname.path))
                lo, hi = struct.unpack(
                    "<II",
                    struct.pack("<d", inferred.qualname.const.value),
                )
                self.memory[lo_slot].value = lo if lo < 0x80000000 else lo - 0x100000000
                self.memory[hi_slot].value = hi if hi < 0x80000000 else hi - 0x100000000
            elif isinstance(inferred.qualname, BooleanConstQualName):
                slot = self.memory.get_slot(inferred.qualname.path)
                self.memory[slot].value = [0, 1][inferred.qualname.const]
            elif isinstance(inferred.qualname, StringConstQualName):
                slot = self.memory.get_slot(inferred.qualname.path)
                length_slot = self.memory.get_slot(Memory.to_string_length(inferred.qualname.path))
                self.memory[length_slot].value = len(inferred.qualname.const)
                self.memory[slot].value = length_slot
                for i, char in enumerate(inferred.qualname.const):
                    self.memory[length_slot + (i + 1) * Memory.WORD_LEN].value = char
            elif isinstance(inferred.qualname, DefinitionQualName):
                inferred_token = inferred.token
                assert not isinstance(inferred_token, VirtualToken)
                token_s_expr = inferred_token.s_expr
                if isinstance(token_s_expr, (SExprDefun, SExprLambda)):
                    tag_slot = self.memory.get_tag_slot(inferred.qualname.path)
                    self.memory[tag_slot].value = self.find_unit_index(inferred.qualname.path)
                    slot = self.memory.get_slot(inferred.qualname.path)
                    self.memory[slot].value = tag_slot
            # else:
            #    assert_never(inferred.qualname)

    @staticmethod
    def emit_load_k(unit: BytecodeUnit, k: int):
        unit.bytecode.extend(
            [
                BC.LOAD_MEM,
                k,
                BC.STORE_MEM,
                Memory.K,
            ]
        )

    @staticmethod
    def emit_load_k_args(unit: BytecodeUnit, args: Sequence[int]):
        unit.bytecode.extend(
            [
                c
                for arg_scr, arg_dst in zip(args, Memory.arg_slots(), strict=False)
                for c in [
                    BC.LOAD_MEM,
                    arg_scr,
                    BC.STORE_MEM,
                    arg_dst,
                ]
            ]
        )

    @staticmethod
    def emit_write_args_inplace(unit: BytecodeUnit, args_builder: Sequence[Sequence[int]]):
        unit.bytecode.extend(
            [
                c
                for arg_builder, arg_dst in zip(args_builder, Memory.arg_slots(), strict=False)
                for c in [*arg_builder, BC.STORE_MEM, arg_dst]
            ]
        )

    @staticmethod
    def emit_apply_k(unit: BytecodeUnit):
        """Передать управление в k_apply (непрямой вызов функции)."""
        unit.bytecode.extend([BC.JMP, -1])
        unit.incomplete_indicies.append(
            IncompleteJmpIndex(len(unit.bytecode) - 1, Compiler.UNIT_K_APPLY)
        )
