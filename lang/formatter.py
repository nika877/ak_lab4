"""Человекочитаемый вывод скомпилированного байткода.

Печатает память (слоты переменных) и команды с мнемониками (LOAD, JMP, HALT...).
Используется в interpreter.py для отладки.
"""

from lang.compiler import BC, CompilationResultMeta, Memory
from lang.compiler.bytecode import WordMemory


def _unit_start(i: int, meta: CompilationResultMeta):
    """Найти имя функции/блока, с которого начинается код по адресу i."""
    if i < len(meta.memory.slots) * Memory.WORD_LEN:
        return None

    i_cnt = len(meta.memory.slots) * Memory.WORD_LEN
    for unit in meta.processed_units:
        if i == i_cnt:
            return unit.path
        i_cnt += len(unit.bytecode) * Memory.WORD_LEN


def _print_bytecode(bc: WordMemory, meta: CompilationResultMeta, offset=0, padding=4):
    """Печать памяти и команд с подписями слотов и мнемониками."""
    i = offset
    print("memory:")
    while i < len(bc):
        if start := _unit_start(i, meta):
            print(f"\n{start}:")

        word_val = bc[i]
        print(f"{' ' * padding}{i:04} = {word_val:04}  |  ", end=" ")

        slot_idx = i // Memory.WORD_LEN
        if slot_idx < len(meta.memory.slots):
            print(f"({meta.memory.slots[slot_idx].path})")
            i += Memory.WORD_LEN
            continue

        opcode = bc[i]
        operand_addr = i + Memory.WORD_LEN

        match opcode:
            case BC.HALT:
                print("HALT")
            case BC.IRET:
                print("IRET")
            case BC.INT:
                print("INT")

            case BC.LOAD_IMM:
                imm = bc[operand_addr]
                if s := _unit_start(imm, meta):
                    print(f"LOAD #{imm} (start of {s})")
                else:
                    print(f"LOAD #{imm}")
                i += Memory.WORD_LEN

            case BC.LOAD_MEM:
                ptr = bc[operand_addr]
                slot_idx = ptr // Memory.WORD_LEN
                if slot_idx < len(meta.memory.slots):
                    print(f"LOAD [{ptr}] ({meta.memory.slots[slot_idx].path})")
                else:
                    print(f"LOAD [{ptr}]")
                i += Memory.WORD_LEN

            case BC.STORE_MEM:
                ptr = bc[operand_addr]
                slot_idx = ptr // Memory.WORD_LEN
                if slot_idx < len(meta.memory.slots):
                    print(f"STORE [{ptr}] ({meta.memory.slots[slot_idx].path})")
                else:
                    print(f"STORE [{ptr}]")
                i += Memory.WORD_LEN

            case BC.EQ_IMM | BC.NE_IMM | BC.LT_IMM | BC.LE_IMM | BC.GT_IMM | BC.GE_IMM:
                imm = bc[operand_addr]
                names: dict[int, str] = {
                    BC.EQ_IMM: "EQ",
                    BC.NE_IMM: "NE",
                    BC.LT_IMM: "LT",
                    BC.LE_IMM: "LE",
                    BC.GT_IMM: "GT",
                    BC.GE_IMM: "GE",
                }
                print(f"{names[opcode]} #{imm}")
                i += Memory.WORD_LEN

            case (
                BC.ADD_IMM
                | BC.SUB_IMM
                | BC.MUL_IMM
                | BC.DIV_IMM
                | BC.MOD_IMM
                | BC.AND_IMM
                | BC.OR_IMM
                | BC.ASL_IMM
                | BC.ASR_IMM
                | BC.LSR_IMM
            ):
                imm = bc[operand_addr]
                names = {
                    BC.ADD_IMM: "ADD",
                    BC.SUB_IMM: "SUB",
                    BC.MUL_IMM: "MUL",
                    BC.DIV_IMM: "DIV",
                    BC.MOD_IMM: "MOD",
                    BC.AND_IMM: "AND",
                    BC.OR_IMM: "OR",
                    BC.ASL_IMM: "ASL",
                    BC.ASR_IMM: "ASR",
                    BC.LSR_IMM: "LSR",
                }
                print(f"{names[opcode]} #{imm}")
                i += Memory.WORD_LEN

            case BC.EQ_MEM | BC.NE_MEM | BC.LT_MEM | BC.LE_MEM | BC.GT_MEM | BC.GE_MEM:
                ptr = bc[operand_addr]
                slot_idx = ptr // Memory.WORD_LEN
                names = {
                    BC.EQ_MEM: "EQ",
                    BC.NE_MEM: "NE",
                    BC.LT_MEM: "LT",
                    BC.LE_MEM: "LE",
                    BC.GT_MEM: "GT",
                    BC.GE_MEM: "GE",
                }
                if slot_idx < len(meta.memory.slots):
                    print(f"{names[opcode]} [{ptr}] ({meta.memory.slots[slot_idx].path})")
                else:
                    print(f"{names[opcode]} [{ptr}]")
                i += Memory.WORD_LEN

            case (
                BC.ADD_MEM
                | BC.SUB_MEM
                | BC.MUL_MEM
                | BC.DIV_MEM
                | BC.MOD_MEM
                | BC.AND_MEM
                | BC.OR_MEM
                | BC.ASL_MEM
                | BC.ASR_MEM
                | BC.LSR_MEM
            ):
                ptr = bc[operand_addr]
                slot_idx = ptr // Memory.WORD_LEN
                names = {
                    BC.ADD_MEM: "ADD",
                    BC.SUB_MEM: "SUB",
                    BC.MUL_MEM: "MUL",
                    BC.DIV_MEM: "DIV",
                    BC.MOD_MEM: "MOD",
                    BC.AND_MEM: "AND",
                    BC.OR_MEM: "OR",
                    BC.ASL_MEM: "ASL",
                    BC.ASR_MEM: "ASR",
                    BC.LSR_MEM: "LSR",
                }
                if slot_idx < len(meta.memory.slots):
                    print(f"{names[opcode]} [{ptr}] ({meta.memory.slots[slot_idx].path})")
                else:
                    print(f"{names[opcode]} [{ptr}]")
                i += Memory.WORD_LEN

            case BC.JMP | BC.JMP_T:
                target = bc[operand_addr]
                name = "JMP" if opcode == BC.JMP else "JMP_T"
                if s := _unit_start(target, meta):
                    print(f"{name} #{target} (start of {s})")
                else:
                    print(f"{name} #{target}")
                i += Memory.WORD_LEN

            case BC.STORE_IND_MEM:
                ptr_addr = bc[operand_addr]
                slot_idx = ptr_addr // Memory.WORD_LEN
                if slot_idx < len(meta.memory.slots):
                    print(f"STORE INDIRECT [{ptr_addr}] (via {meta.memory.slots[slot_idx].path})")
                else:
                    print(f"STORE INDIRECT [{ptr_addr}]")
                i += Memory.WORD_LEN

            case BC.LOAD_IND_MEM:
                ptr_addr = bc[operand_addr]
                slot_idx = ptr_addr // Memory.WORD_LEN
                if slot_idx < len(meta.memory.slots):
                    print(f"LOAD INDIRECT [{ptr_addr}] (via {meta.memory.slots[slot_idx].path})")
                else:
                    print(f"LOAD INDIRECT [{ptr_addr}]")
                i += Memory.WORD_LEN

            case _:
                print(f"? (opcode {opcode})")

        i += Memory.WORD_LEN


def print_bytecode(bc: bytes, meta: CompilationResultMeta):
    """Публичная обёртка: дамп байткода в stdout."""
    _print_bytecode(WordMemory(bc, Memory.WORD_LEN), meta)
