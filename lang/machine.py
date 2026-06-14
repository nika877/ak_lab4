#!/usr/bin/python3
"""Модель процессора: ControlUnit + DataPath.

Вариант: **lisp | acc | neum | hw | tick | binary | trap | mem | pstr | prob1 | superscalar**.

Модуль содержит три ключевые сущности:
- `DataPath` — пассивный тракт данных (память, ALU, регистры, порты).
- `ControlUnit` — активный блок управления (PC, IR, step-counter, декодер, выборка).
- `simulation` / `main` — функции запуска модели.

Все сигналы "защёлкивания" выполняются за один такт. Корректность их
последовательности обеспечивает ControlUnit (это и есть hardwired-логика).
"""

from __future__ import annotations

import logging
import struct
from collections.abc import Iterable
from dataclasses import dataclass
from io import StringIO

from lang.compiler.bytecode import BC, WordMemory
from lang.compiler.memory import Memory
from lang.isa import (
    DECODE,
    WORD_LEN,
    ZERO_ARG_OPCODES,
    AluOp,
    ArgSrc,
    decode_word,
)


def _build_memory(image: bytes, total_size: int) -> WordMemory:
    """Поднять `WordMemory` нужного размера на основе байтового образа."""
    assert len(image) <= total_size, "image larger than memory"
    padded = bytes(image) + bytes(total_size - len(image))
    return WordMemory(padded, WORD_LEN)


class DataPath:
    """Тракт данных. Реализует:
    - регистры: `acc`, `addr`, `data_reg`, `alu_out`;
    - память: единое адресное пространство (фон-Нейман);
    - порты: `PORT_IN`/`PORT_OUT` (memory-mapped);
    - ALU c набором операций из `AluOp`;
    - флаги: `zero` (Z) -- используются ControlUnit'ом для JMP_T.

    Каждый `signal_*` имитирует один тактовый сигнал и выполняется за 1 такт.
    Корректность последовательности сигналов обеспечивает ControlUnit.
    """

    memory: WordMemory
    "Память (единое пространство кода + данных + портов)."

    acc: int
    "Аккумулятор (signed int32)."

    addr: int
    "Защёлкнутый адрес. Используется для signal_oe и signal_wr."

    data_reg: int
    "Регистр данных (значение, прочитанное из памяти на предыдущем такте)."

    alu_out: int
    "Выход ALU (обновляется как только установлены операнды и op)."

    output_buffer: list[str]
    "Накопитель символов, отправленных в PORT_OUT (для отладки/проверки)."

    def __init__(self, memory_image: bytes, total_memory: int):
        self.memory = _build_memory(memory_image, total_memory)
        self.acc = 0
        self.addr = 0
        self.data_reg = 0
        self.alu_out = 0
        self.output_buffer = []

    # ── флаги ──────────────────────────────────────────────────────────────────

    @property
    def zero(self) -> bool:
        """Флаг нуля (Z). Используется ControlUnit'ом для JMP_T (JMP_T = if !zero)."""
        return self.acc == 0

    # ── сигналы защёлкивания (== "за один такт") ───────────────────────────────

    def signal_latch_addr(self, value: int) -> None:
        """Защёлкнуть адрес в регистр `addr`. `value` подаётся либо из PC, либо
        из аргумента IR (немедленное), либо из ячейки памяти (косвенное).
        Выбор источника делает ControlUnit."""
        assert 0 <= value < len(self.memory), f"address out of memory: {value}"
        self.addr = value

    def signal_oe(self) -> None:
        """Output Enable -- защёлкнуть в `data_reg` слово из памяти по адресу `addr`.
        Это синхронное чтение (соответствует фронту такта)."""
        self.data_reg = self.memory[self.addr]

    def signal_alu(self, op: AluOp, arg: int) -> None:
        """Скомбинировать `acc` и `arg` через ALU, поместить результат в `alu_out`.

        Это комбинационная логика, не имеет своей задержки -- но для tick-точности
        вынесена в отдельный шаг (== один такт). `arg` приходит от arg_mux
        (либо немедленное из IR, либо `data_reg`).
        """
        a = self.acc
        b = arg
        mask = (1 << (8 * WORD_LEN)) - 1
        sign_bit = 1 << (8 * WORD_LEN - 1)
        match op:
            case AluOp.PASS_ARG:
                out = b
            case AluOp.ADD:
                out = a + b
            case AluOp.SUB:
                out = a - b
            case AluOp.MUL:
                out = a * b
            case AluOp.DIV:
                out = a // b
            case AluOp.MOD:
                out = a % b
            case AluOp.AND:
                out = a & b
            case AluOp.OR:
                out = a | b
            case AluOp.ASL:
                out = (a << b) & mask
                if out & sign_bit:
                    out -= 1 << (8 * WORD_LEN)
            case AluOp.ASR:
                # Арифметический сдвиг с расширением знака.
                out = a >> b
                if a < 0:
                    out |= ((1 << b) - 1) << (8 * WORD_LEN - b)
            case AluOp.LSR:
                out = (a & mask) >> b
            case AluOp.EQ:
                out = 1 if a == b else 0
            case AluOp.NE:
                out = 1 if a != b else 0
            case AluOp.LT:
                out = 1 if a < b else 0
            case AluOp.LE:
                out = 1 if a <= b else 0
            case AluOp.GT:
                out = 1 if a > b else 0
            case AluOp.GE:
                out = 1 if a >= b else 0
            case _:
                raise AssertionError(f"unknown alu op: {op}")

        # Усечение результата до signed int32 (для соответствия железу).
        out &= mask
        if out & sign_bit:
            out -= 1 << (8 * WORD_LEN)
        self.alu_out = out

    def signal_latch_acc(self, sel: str) -> None:
        """Защёлкнуть `acc` из выбранного источника.
        - sel == "alu" — из выхода ALU (`alu_out`);
        - sel == "mem" — из регистра данных (`data_reg`).
        """
        if sel == "alu":
            self.acc = self.alu_out
        elif sel == "mem":
            self.acc = self.data_reg
        else:
            raise AssertionError(f"unknown latch_acc sel: {sel}")

    def signal_wr(self, value: int) -> None:
        """Записать значение в память по адресу `addr`. Источник `value` -- обычно
        это `acc` (для STORE_MEM/STORE_IND_MEM). Если адрес = `Memory.PORT_OUT`,
        дополнительно поднимается сигнал signal_output -- значение декодируется
        как UTF-32 символ и попадает в output buffer.
        """
        self.memory[self.addr] = value
        if self.addr == Memory.PORT_OUT:
            self.signal_output(value)

    def signal_output(self, value: int) -> None:
        """Преобразовать слово в UTF-32 символ и положить в output_buffer.
        Реализует port-mapped I/O на выход (см. вариант 'mem' + 'pstr')."""
        word = value & 0xFFFFFFFF
        char = word.to_bytes(4, "little").decode("utf-32le", errors="replace")
        logging.debug("output: %r << %r", "".join(self.output_buffer), char)
        self.output_buffer.append(char)

    def signal_port_in(self, value: int) -> None:
        """Имитация фронта trap'а: внешнее устройство (контроллер ввода) кладёт
        слово в `PORT_IN`. Сама обработка прерывания делается ControlUnit'ом."""
        self.memory[Memory.PORT_IN] = value


@dataclass(slots=True)
class InstructionRegister:
    """Регистр инструкции. Хранит опкод и аргумент текущей команды.

    Адрес начала инструкции (`pc_of_instr`) сохраняется для лога / диагностики:
    после декодирования PC уже может указывать на следующий опкод."""

    pc_of_instr: int = 0
    opcode: int = 0
    arg: int = 0


@dataclass(slots=True)
class SavedState:
    """Сохранённое состояние для IRET."""

    pc: int
    acc: int


class HaltError(Exception):
    """Сигнальное исключение: достигнут BC.HALT."""


class ControlUnit:
    """Hardwired блок управления.

    Управляет PC, регистром IR, декодирует и эмитит сигналы для DataPath.
    Поддерживает trap-based прерывания (`trap_queue`).
    """

    data_path: DataPath
    program_counter: int
    code_start: int
    "Адрес первого слова кода (всё, что до -- область памяти данных)."

    ir: InstructionRegister
    step: int
    "Текущий шаг текущей инструкции (см. описание выше)."

    _tick: int
    _instr_count: int
    "Счётчик инструкций, выполненных как 'second slot' super scalar-пары."

    saved: SavedState | None
    "Сохранённое состояние при обработке прерывания. None — мы не в ISR."

    trap_queue: list[tuple[int, int]]
    "Очередь прерываний от устройства ввода: [(tick_at_or_after, value), ...]."

    output_stream: StringIO

    log: list[str]
    log_print_on_append: bool

    def __init__(
        self,
        data_path: DataPath,
        entry_point: int,
        code_start: int,
        input_data: list[int],
        output_stream: StringIO,
        auto_print_log: bool,
    ):
        self.data_path = data_path
        self.program_counter = entry_point
        self.code_start = code_start
        self.ir = InstructionRegister()
        self.step = 0
        self._tick = 0
        self._instr_count = 0
        self.saved = None
        # Совместимо с runtime.py: вводы поступают на тиках 200, 400, 600, ...
        self.trap_queue = [(200 * (i + 1), v) for i, v in enumerate(input_data)]
        self.output_stream = output_stream
        self.log = []
        self.log_print_on_append = auto_print_log

    # ── управление модельным временем ─────────────────────────────────────────

    def tick(self) -> None:
        self._tick += 1

    @property
    def current_tick(self) -> int:
        return self._tick

    @property
    def instr_count(self) -> int:
        return self._instr_count

    def _append_log(self, msg: str) -> None:
        line = f"({self._tick:04}) {msg}"
        self.log.append(line)
        if self.log_print_on_append:
            print(line)

    # ── главный цикл: один такт = одна микрооперация

    def process_next_tick(self) -> None:
        """Один такт ControlUnit. Делегирует на step-функцию текущего шага.

        Порядок:
          1. Если включён trap и пришло время — переключиться в ISR.
          2. Выполнить микрооперацию для текущего step.
        """
        # 1) Trap (input) — проверяется только в начале инструкции, чтобы не
        # разрывать выборку/декод.
        if (
            self.step == 0
            and self.saved is None
            and self.trap_queue
            and self._tick >= self.trap_queue[0][0]
        ):
            tick_at, value = self.trap_queue.pop(0)
            self._append_log(f"INT  port_in <- {value}")
            self.saved = SavedState(self.program_counter, self.data_path.acc)
            self.data_path.signal_port_in(value)
            handler = self.data_path.memory[Memory.INT_VECTOR_INPUT]
            self.program_counter = handler
            self.tick()
            return

        # 2) Выполнить шаг текущей инструкции. Если шаг — это EXECUTE и опкод
        # достаточно "лёгкий", выполнение может занять 0 дополнительных тактов
        # (всё уместилось в одном микро-шаге).
        _ = self._run_step()
        self.tick()

    # ── ступени конвейера ─────────────────────────────────────────────────────

    def _run_step(self) -> bool:
        """Выполнить один микрошаг. Возвращает True, если инструкция полностью
        завершилась на этом такте (PC уже указывает на следующую)."""
        if self.step == 0:
            self._stage_fetch()
            return False
        if self.step == 1:
            # OPERAND fetch (если инструкция двухсловная) либо переход сразу к EX.
            if self._is_zero_arg(self.ir.opcode):
                # 1-словная инструкция: сразу EXECUTE.
                return self._stage_execute()
            self._stage_operand()
            return False
        if self.step == 2:
            # ADDRESS (для *_MEM / IND_MEM) либо сразу EXECUTE.
            decoded = DECODE[self.ir.opcode]
            if decoded.arg_src == ArgSrc.MEM:
                self._stage_address_direct()
                return False
            if decoded.arg_src == ArgSrc.IND_MEM:
                self._stage_address_indirect_1()
                return False
            # IMM / NONE -- адресной фазы нет, сразу выполняем.
            return self._stage_execute()
        if self.step == 3:
            decoded = DECODE[self.ir.opcode]
            if decoded.arg_src == ArgSrc.IND_MEM:
                self._stage_address_indirect_2()
                return False
            return self._stage_execute()
        if self.step == 4:
            return self._stage_execute()
        raise AssertionError(f"bad step: {self.step}")

    def _stage_fetch(self) -> None:
        """FETCH: addr ← PC; data_reg ← M[addr]; IR.opcode ← data_reg.

        В реальном железе это две микрооперации (latch_addr, oe), но мы их
        совмещаем в одном такте — это эквивалент одного фронта clock, при
        котором адрес устанавливается и сразу же читается слово (асинхронный
        вывод памяти). Это упрощение допустимо в рамках модели и сильно
        уменьшает накладные расходы по тактам.
        """
        self.ir.pc_of_instr = self.program_counter
        self.data_path.signal_latch_addr(self.program_counter)
        self.data_path.signal_oe()
        self.ir.opcode = decode_word(self.data_path.data_reg)
        self.program_counter += WORD_LEN
        self.step = 1
        if self.ir.opcode not in DECODE:
            raise AssertionError(f"bad opcode 0x{self.ir.opcode:X} at PC=0x{self.ir.pc_of_instr:X}")

    def _stage_operand(self) -> None:
        """OPERAND: addr ← PC; data_reg ← M[addr]; IR.arg ← data_reg.

        Для двухсловных инструкций второе слово -- аргумент."""
        self.data_path.signal_latch_addr(self.program_counter)
        self.data_path.signal_oe()
        self.ir.arg = self.data_path.data_reg
        self.program_counter += WORD_LEN
        self.step = 2

    def _stage_address_direct(self) -> None:
        """ADDRESS (direct): addr ← IR.arg; data_reg ← M[addr]."""
        self.data_path.signal_latch_addr(self.ir.arg)
        self.data_path.signal_oe()
        self.step = 3

    def _stage_address_indirect_1(self) -> None:
        """ADDRESS (indirect, phase 1): прочесть указатель из M[IR.arg]."""
        self.data_path.signal_latch_addr(self.ir.arg)
        self.data_path.signal_oe()
        # data_reg теперь содержит реальный адрес (pointer)
        self.step = 3

    def _stage_address_indirect_2(self) -> None:
        """ADDRESS (indirect, phase 2): прочесть значение из M[pointer]."""
        pointer = self.data_path.data_reg
        self.data_path.signal_latch_addr(pointer)
        # Для STORE_IND_MEM -- не нужно oe, нам нужен только адрес для записи.
        # Для LOAD_IND_MEM -- читаем значение.
        if self.ir.opcode == BC.LOAD_IND_MEM:
            self.data_path.signal_oe()
        self.step = 4

    def _stage_execute(self) -> bool:
        """EXECUTE: применить ALU / writeback / PC-управление.
        Возвращает True (инструкция завершена). Сбрасывает `step` в 0."""
        op = self.ir.opcode
        arg = self.ir.arg

        # ── Управляющие инструкции ──────────────────────────────────────────
        if op == BC.HALT:
            self._append_log(f"[{self.ir.pc_of_instr:04}] HALT")
            self._instr_count += 1
            raise HaltError()

        if op == BC.INT:
            # Программный INT: не влияет на наш hardware-trap, просто NOP.
            self._append_log(f"[{self.ir.pc_of_instr:04}] [int]")
            self.step = 0
            self._instr_count += 1
            return True

        if op == BC.IRET:
            assert self.saved is not None, "IRET without active interrupt"
            self.program_counter = self.saved.pc
            self.data_path.acc = self.saved.acc
            self.saved = None
            self._append_log(f"[{self.ir.pc_of_instr:04}] IRET")
            self.step = 0
            self._instr_count += 1
            return True

        if op == BC.JMP:
            self.program_counter = arg
            self._append_log(f"[{self.ir.pc_of_instr:04}] JMP -> {arg}")
            self.step = 0
            self._instr_count += 1
            return True

        if op == BC.JMP_T:
            # JMP_T: переход, если acc != 0 (используется как "истинное" условие).
            if not self.data_path.zero:
                self.program_counter = arg
                self._append_log(
                    f"[{self.ir.pc_of_instr:04}] JMP_T (acc={self.data_path.acc}) -> {arg}"
                )
            else:
                self._append_log(f"[{self.ir.pc_of_instr:04}] JMP_T (acc=0) skip")
            self.step = 0
            self._instr_count += 1
            return True

        # ── STORE_MEM / STORE_IND_MEM ───────────────────────────────────────
        if op == BC.STORE_MEM:
            self.data_path.signal_latch_addr(arg)
            self.data_path.signal_wr(self.data_path.acc)
            self._append_log(
                f"[{self.ir.pc_of_instr:04}] mem[{arg}] = acc -> mem[{arg}] = {self.data_path.acc}"
            )
            self._maybe_flush_port_out(arg)
            self.step = 0
            self._instr_count += 1
            return True

        if op == BC.STORE_IND_MEM:
            # На шаге _stage_address_indirect_2 уже защёлкнули реальный addr.
            self.data_path.signal_wr(self.data_path.acc)
            self._append_log(
                f"[{self.ir.pc_of_instr:04}] mem[mem[{arg}]] = acc -> "
                f"mem[{self.data_path.addr}] = {self.data_path.acc}"
            )
            self._maybe_flush_port_out(self.data_path.addr)
            self.step = 0
            self._instr_count += 1
            return True

        # ── ALU / LOAD ──────────────────────────────────────────────────────
        decoded = DECODE[op]
        # Выбор аргумента для ALU (из arg_mux):
        if decoded.arg_src == ArgSrc.IMM:
            alu_arg = arg
            human = f"#{arg}"
        elif decoded.arg_src == ArgSrc.MEM:
            alu_arg = self.data_path.data_reg
            human = f"mem[{arg}]={alu_arg}"
        elif decoded.arg_src == ArgSrc.IND_MEM:
            alu_arg = self.data_path.data_reg
            human = f"mem[mem[{arg}]]={alu_arg}"
        else:
            alu_arg = 0
            human = "-"

        self.data_path.signal_alu(decoded.alu, alu_arg)
        self.data_path.signal_latch_acc("alu")
        self._append_log(
            f"[{self.ir.pc_of_instr:04}] {BC(op).name:<13} {human:<20}-> acc = {self.data_path.acc}"
        )
        self.step = 0
        self._instr_count += 1
        return True

    def _maybe_flush_port_out(self, addr: int) -> None:
        """Если запись пошла в PORT_OUT — продублировать вывод в output_stream
        (для тех тестов, которые читают output как string).
        """
        if addr == Memory.PORT_OUT:
            # signal_wr уже положил символ в data_path.output_buffer
            # (см. DataPath.signal_output). Дублируем в stream.
            self.output_stream.write(self.data_path.output_buffer[-1])

    @staticmethod
    def _is_zero_arg(opcode: int) -> bool:
        return opcode in ZERO_ARG_OPCODES

    # ── repr для логов ────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"TICK: {self._tick:5} "
            f"PC: 0x{self.program_counter:04X} "
            f"STEP: {self.step} "
            f"IR: {BC(self.ir.opcode).name:<13} arg={self.ir.arg} "
            f"ACC: {self.data_path.acc} "
            f"ADDR: 0x{self.data_path.addr:04X} "
            f"DATA: {self.data_path.data_reg}"
        )


# ────────────────────────────────────────────────────────────────────────────────
# Драйвер модели
# ────────────────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class SimulationResult:
    acc: int
    output: str
    log: list[str]
    ticks: int
    instructions: int


def simulation(
    image: bytes,
    entry_point: int,
    code_start: int,
    input_data: Iterable[int] = (),
    *,
    extra_memory: int = 1_000_000,
    tick_limit: int = 10_000_000,
    auto_print_log: bool = False,
) -> SimulationResult:
    """Запустить модель.

    Параметры:
        image       -- бинарный образ (память данных + код, как его собирает Compiler).
        entry_point -- адрес первой инструкции main (в байтах от начала памяти).
        code_start  -- адрес начала области кода (для отладки/дампа).
        input_data  -- список int-значений, поступающих через trap по timeline.
        extra_memory-- сколько байт памяти добавить сверх образа (под heap).
        tick_limit  -- предел по тактам (для защиты от бесконечных циклов).
        auto_print_log -- печатать ли лог построчно по ходу симуляции.

    Возвращает `SimulationResult` с финальным acc, выводом, логом и метриками.
    """
    total = len(image) + extra_memory
    dp = DataPath(image, total)
    out = StringIO()
    cu = ControlUnit(
        dp,
        entry_point,
        code_start,
        list(input_data),
        out,
        auto_print_log=auto_print_log,
    )

    try:
        while cu.current_tick < tick_limit:
            cu.process_next_tick()
    except HaltError:
        pass

    if cu.current_tick >= tick_limit:
        logging.warning("Tick limit reached (%d)", tick_limit)

    return SimulationResult(
        acc=dp.acc,
        output=out.getvalue(),
        log=cu.log,
        ticks=cu.current_tick,
        instructions=cu.instr_count,
    )


def main(code_path: str, input_path: str | None = None) -> None:
    """CLI-обёртка: запустить модель из бинарного образа.

    Формат бинарника совпадает с тем, что отдаёт `Compiler.compile(...).bytecode`.
    Точка входа хранится отдельно (через JSON-метаданные или через переменные
    окружения; в рамках лабы — передаётся через input_path как пара 'image,offset').
    Для простоты в этом CLI считаем, что image -- это просто bytes, а entry_point
    задаётся первым 4-байтовым словом отдельного meta-файла '<code_path>.entry'.
    """
    with open(code_path, "rb") as f:
        image = f.read()
    try:
        with open(code_path + ".entry", "rb") as f:
            entry_point = struct.unpack("<i", f.read(4))[0]
            code_start = struct.unpack("<i", f.read(4))[0]
    except FileNotFoundError:
        entry_point = 0
        code_start = 0

    tokens: list[int] = []
    if input_path:
        with open(input_path, encoding="utf-8") as f:
            for ch in f.read():
                tokens.append(ord(ch))

    res = simulation(image, entry_point, code_start, tokens)
    print(res.output, end="")
    print(f"\nACC: {res.acc}")
    print(f"ticks: {res.ticks}  instructions: {res.instructions}")


if __name__ == "__main__":
    import sys

    logging.getLogger().setLevel(logging.DEBUG)
    assert len(sys.argv) in (2, 3), "machine.py <code_file> [<input_file>]"
    main(sys.argv[1], sys.argv[2] if len(sys.argv) == 3 else None)
