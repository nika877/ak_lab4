"""Программный интерпретатор байткода (упрощённая модель процессора).

Это НЕ аппаратная модель! Для симуляции железа с тактами и ControlUnit
используй lang.machine.simulation.

Здесь команды исполняются напрямую в Python: читаем опкод, меняем acc и PC.
Поддерживает trap-ввод (символы приходят на тиках 200, 400, 600...) и вывод
через PORT_OUT.
"""

from io import StringIO
from time import sleep

from lang.compiler import BC
from lang.compiler.bytecode import WordMemory
from lang.compiler.memory import Memory


def interpret(
    bytecode: bytes,
    entry_point: int,
    input_data: list[int] | None = None,
    output_stream: StringIO | None = None,
    auto_print_log: bool = False,
    delay_s: float = 0.0,
):
    """Выполнить байткод и вернуть (acc, вывод, лог).

    bytecode     — бинарный образ (память + код)
    entry_point  — адрес первой инструкции main (в байтах)
    input_data   — символы для (input), приходят через trap
    output_stream — куда писать вывод print
    auto_print_log — печатать лог по ходу выполнения
    delay_s      — пауза между тактами (для отладки)
    """
    if output_stream is None:
        output_stream = StringIO()

    if input_data is None:
        input_data = []

    bc = WordMemory(bytecode, Memory.WORD_LEN)
    bc.inner.extend([0] * 1_000_000)  # запас памяти под кучу (heap)
    ip = entry_point  # указатель инструкций (Program Counter)
    acc = 0  # аккумулятор — главный регистр
    log: list[str] = []
    last_printed_idx = 0

    # Очередь trap-событий: ввод приходит на фиксированных тиках
    trap_queue = [(200 * (i + 1), val) for i, val in enumerate(input_data)]
    tick = -1
    restore = None  # сохранённое (ip, acc) при входе в обработчик прерывания

    try:
        while True:
            if delay_s != 0:
                sleep(delay_s)
            tick += 1

            if auto_print_log:
                print("\n".join(log[last_printed_idx:]))
                last_printed_idx = len(log)

            # Trap: имитация прерывания ввода — переход в ISR
            if trap_queue and tick == trap_queue[0][0]:
                log.append(f"({tick:04}) INT")
                restore = ip, acc
                ip = bc[Memory.INT_VECTOR_INPUT]
                bc[Memory.PORT_IN] = trap_queue[0][1]
                trap_queue.pop(0)
                continue

            opcode = bc[ip]

            # Диспетчеризация по опкоду — каждая ветка = одна машинная команда
            match opcode:
                case BC.IRET:
                    log.append(f"({tick:04}) IRET")
                    assert restore is not None
                    ip, acc = restore
                    restore = None
                    continue

                case BC.HALT:
                    log.append(f"({tick:04}) [{ip:04}] HALT")
                    break

                case BC.LOAD_IMM:
                    acc = bc[ip + Memory.WORD_LEN]
                    log.append(f"({tick:04}) [{ip:04}] acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.LOAD_MEM:
                    ptr = bc[ip + Memory.WORD_LEN]
                    acc = bc[ptr]
                    log.append(f"({tick:04}) [{ip:04}] acc = mem[{ptr}] -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.STORE_MEM:
                    ptr = bc[ip + Memory.WORD_LEN]
                    bc[ptr] = acc
                    log.append(f"({tick:04}) [{ip:04}] mem[{ptr}] = acc -> mem[{ptr}] = {acc}")
                    if ptr == Memory.PORT_OUT:
                        char = acc.to_bytes(4, "little").decode("utf-32le")
                        output_stream.write(char)
                    ip += 2 * Memory.WORD_LEN

                case BC.EQ_IMM:
                    imm = bc[ip + Memory.WORD_LEN]
                    acc = 1 if acc == imm else 0
                    log.append(f"({tick:04}) [{ip:04}] acc = acc == {imm} -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.NE_IMM:
                    imm = bc[ip + Memory.WORD_LEN]
                    acc = 1 if acc != imm else 0
                    log.append(f"({tick:04}) [{ip:04}] acc = acc != {imm} -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.LT_IMM:
                    imm = bc[ip + Memory.WORD_LEN]
                    acc = 1 if acc < imm else 0
                    log.append(f"({tick:04}) [{ip:04}] acc = acc < {imm} -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.LE_IMM:
                    imm = bc[ip + Memory.WORD_LEN]
                    acc = 1 if acc <= imm else 0
                    log.append(f"({tick:04}) [{ip:04}] acc = acc <= {imm} -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.GT_IMM:
                    imm = bc[ip + Memory.WORD_LEN]
                    acc = 1 if acc > imm else 0
                    log.append(f"({tick:04}) [{ip:04}] acc = acc > {imm} -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.GE_IMM:
                    imm = bc[ip + Memory.WORD_LEN]
                    acc = 1 if acc >= imm else 0
                    log.append(f"({tick:04}) [{ip:04}] acc = acc >= {imm} -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.ADD_IMM:
                    imm = bc[ip + Memory.WORD_LEN]
                    acc = acc + imm
                    log.append(f"({tick:04}) [{ip:04}] acc = acc + {imm} -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.SUB_IMM:
                    imm = bc[ip + Memory.WORD_LEN]
                    acc = acc - imm
                    log.append(f"({tick:04}) [{ip:04}] acc = acc - {imm} -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.MUL_IMM:
                    imm = bc[ip + Memory.WORD_LEN]
                    acc = acc * imm
                    log.append(f"({tick:04}) [{ip:04}] acc = acc * {imm} -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.DIV_IMM:
                    imm = bc[ip + Memory.WORD_LEN]
                    acc = acc // imm
                    log.append(f"({tick:04}) [{ip:04}] acc = acc // {imm} -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.MOD_IMM:
                    imm = bc[ip + Memory.WORD_LEN]
                    acc = acc % imm
                    log.append(f"({tick:04}) [{ip:04}] acc = acc % {imm} -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.EQ_MEM:
                    ptr = bc[ip + Memory.WORD_LEN]
                    mem_val = bc[ptr]
                    acc = 1 if acc == mem_val else 0
                    log.append(f"({tick:04}) [{ip:04}] acc = acc == mem[{ptr}] -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.NE_MEM:
                    ptr = bc[ip + Memory.WORD_LEN]
                    mem_val = bc[ptr]
                    acc = 1 if acc != mem_val else 0
                    log.append(f"({tick:04}) [{ip:04}] acc = acc != mem[{ptr}] -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.LT_MEM:
                    ptr = bc[ip + Memory.WORD_LEN]
                    mem_val = bc[ptr]
                    acc = 1 if acc < mem_val else 0
                    log.append(f"({tick:04}) [{ip:04}] acc = acc < mem[{ptr}] -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.LE_MEM:
                    ptr = bc[ip + Memory.WORD_LEN]
                    mem_val = bc[ptr]
                    acc = 1 if acc <= mem_val else 0
                    log.append(f"({tick:04}) [{ip:04}] acc = acc <= mem[{ptr}] -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.GT_MEM:
                    ptr = bc[ip + Memory.WORD_LEN]
                    mem_val = bc[ptr]
                    acc = 1 if acc > mem_val else 0
                    log.append(f"({tick:04}) [{ip:04}] acc = acc > mem[{ptr}] -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.GE_MEM:
                    ptr = bc[ip + Memory.WORD_LEN]
                    mem_val = bc[ptr]
                    acc = 1 if acc >= mem_val else 0
                    log.append(f"({tick:04}) [{ip:04}] acc = acc >= mem[{ptr}] -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.ADD_MEM:
                    ptr = bc[ip + Memory.WORD_LEN]
                    mem_val = bc[ptr]
                    acc = acc + mem_val
                    log.append(f"({tick:04}) [{ip:04}] acc = acc + mem[{ptr}] -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.SUB_MEM:
                    ptr = bc[ip + Memory.WORD_LEN]
                    mem_val = bc[ptr]
                    acc = acc - mem_val
                    log.append(f"({tick:04}) [{ip:04}] acc = acc - mem[{ptr}] -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.AND_MEM:
                    ptr = bc[ip + Memory.WORD_LEN]
                    mem_val = bc[ptr]
                    acc = acc & mem_val
                    log.append(f"({tick:04}) [{ip:04}] acc = acc & mem[{ptr}] -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.OR_MEM:
                    ptr = bc[ip + Memory.WORD_LEN]
                    mem_val = bc[ptr]
                    acc = acc | mem_val
                    log.append(f"({tick:04}) [{ip:04}] acc = acc | mem[{ptr}] -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.ASL_MEM:
                    ptr = bc[ip + Memory.WORD_LEN]
                    mem_val = bc[ptr]
                    mask = (1 << (8 * Memory.WORD_LEN)) - 1
                    acc = (acc << mem_val) & mask
                    log.append(f"({tick:04}) [{ip:04}] acc = acc ASL mem[{ptr}] -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.ASR_MEM:
                    ptr = bc[ip + Memory.WORD_LEN]
                    mem_val = bc[ptr]
                    mask = (1 << (8 * Memory.WORD_LEN)) - 1
                    sign_bit = 1 << ((8 * Memory.WORD_LEN) - 1)
                    acc >>= mem_val
                    if acc & sign_bit:
                        acc |= ((1 << mem_val) - 1) << ((8 * Memory.WORD_LEN) - mem_val)
                    log.append(f"({tick:04}) [{ip:04}] acc = acc ASR mem[{ptr}] -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.LSR_MEM:
                    ptr = bc[ip + Memory.WORD_LEN]
                    mem_val = bc[ptr]
                    acc >>= mem_val
                    log.append(f"({tick:04}) [{ip:04}] acc = acc LSR mem[{ptr}] -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.AND_IMM:
                    imm = bc[ip + Memory.WORD_LEN]
                    acc = acc & imm
                    log.append(f"({tick:04}) [{ip:04}] acc = acc & {imm} -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.OR_IMM:
                    imm = bc[ip + Memory.WORD_LEN]
                    acc = acc | imm
                    log.append(f"({tick:04}) [{ip:04}] acc = acc | {imm} -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.ASL_IMM:
                    imm = bc[ip + Memory.WORD_LEN]
                    mask = (1 << (8 * Memory.WORD_LEN)) - 1
                    acc = (acc << imm) & mask
                    # Sign-extend back to signed int32
                    if acc >= (1 << (8 * Memory.WORD_LEN - 1)):
                        acc -= 1 << (8 * Memory.WORD_LEN)
                    log.append(f"({tick:04}) [{ip:04}] acc = acc ASL {imm} -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.ASR_IMM:
                    imm = bc[ip + Memory.WORD_LEN]
                    mask = (1 << (8 * Memory.WORD_LEN)) - 1
                    sign_bit = 1 << ((8 * Memory.WORD_LEN) - 1)
                    acc >>= imm
                    if acc & sign_bit:
                        acc |= ((1 << imm) - 1) << ((8 * Memory.WORD_LEN) - imm)
                    log.append(f"({tick:04}) [{ip:04}] acc = acc ASR {imm} -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.LSR_IMM:
                    imm = bc[ip + Memory.WORD_LEN]
                    mask = (1 << (8 * Memory.WORD_LEN)) - 1
                    acc = (acc & mask) >> imm
                    log.append(f"({tick:04}) [{ip:04}] acc = acc LSR {imm} -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.MUL_MEM:
                    ptr = bc[ip + Memory.WORD_LEN]
                    mem_val = bc[ptr]
                    acc = acc * mem_val
                    log.append(f"({tick:04}) [{ip:04}] acc = acc * mem[{ptr}] -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.DIV_MEM:
                    ptr = bc[ip + Memory.WORD_LEN]
                    mem_val = bc[ptr]
                    acc = acc // mem_val
                    log.append(f"({tick:04}) [{ip:04}] acc = acc // mem[{ptr}] -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.MOD_MEM:
                    ptr = bc[ip + Memory.WORD_LEN]
                    mem_val = bc[ptr]
                    acc = acc % mem_val
                    log.append(f"({tick:04}) [{ip:04}] acc = acc % mem[{ptr}] -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case BC.JMP:
                    target = bc[ip + Memory.WORD_LEN]
                    log.append(f"({tick:04}) [{ip:04}] ip = {target}")
                    ip = target
                    continue

                case BC.JMP_T:
                    target = bc[ip + Memory.WORD_LEN]
                    if acc:
                        log.append(f"({tick:04}) [{ip:04}] ip = {target}")
                        ip = target
                        continue
                    else:
                        ip += 2 * Memory.WORD_LEN

                case BC.INT:
                    log.append(f"({tick:04}) [{ip:04}] [int]")
                    ip += Memory.WORD_LEN

                case BC.STORE_IND_MEM:
                    ptr_addr = bc[ip + Memory.WORD_LEN]
                    final_addr = bc[ptr_addr]
                    bc[final_addr] = acc
                    log.append(
                        f"({tick:04}) [{ip:04}] mem[mem[{ptr_addr}]] = acc -> mem[{final_addr}] = {acc}"
                    )
                    ip += 2 * Memory.WORD_LEN

                case BC.LOAD_IND_MEM:
                    ptr_addr = bc[ip + Memory.WORD_LEN]
                    final_addr = bc[ptr_addr]
                    acc = bc[final_addr]
                    log.append(f"({tick:04}) [{ip:04}] acc = mem[mem[{ptr_addr}]] -> acc = {acc}")
                    ip += 2 * Memory.WORD_LEN

                case unknown:
                    log_str = "\n".join(log)
                    raise Exception(f"unknown instruction: {unknown} at {ip}\n{log_str}")

    except IndexError:
        log.append("[no heap]")
        acc = -1

    if auto_print_log:
        print("\n".join(log[last_printed_idx:]))

    return acc, output_stream.getvalue(), log
