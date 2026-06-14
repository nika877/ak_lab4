"""ISA (Instruction Set Architecture) для процессора.

В файле определены два представления:
- Бинарное (для загрузки в память команд).
- JSON (для логирования и отладки).

Поскольку машинный код и память данных живут в одном адресном пространстве
(фон-Нейман), инструкции хранятся "словами" (word = 32 бит, little-endian) точно
так же, как и обычные данные. В одной ячейке памяти может находиться либо опкод,
либо число — что именно, определяется ControlUnit'ом в зависимости от значения PC.

Кодировка инструкции (одно или два слова в памяти):

```text
Однословные (HALT, IRET, INT) — занимают 1 слово:

┌─────────────────────────────────────────────────────────────────────┐
│ 31                                                                0 │
├─────────────────────────────────────────────────────────────────────┤
│                            опкод                                    │
└─────────────────────────────────────────────────────────────────────┘

Двухсловные (все остальные: LOAD_MEM, STORE_MEM, ADD_IMM, JMP, ...):

слово N     ┌─────────────────────────────────────────────────────────┐
            │                       опкод                             │
            └─────────────────────────────────────────────────────────┘
слово N+1   ┌─────────────────────────────────────────────────────────┐
            │                  аргумент (32-битное signed)            │
            └─────────────────────────────────────────────────────────┘
```

Так как у нас 43 опкода (см. `BC`), 16-битного поля более чем достаточно
(0..0xFFFF). Старшие 16 бит зарезервированы (заполняются нулями), что оставляет
запас под микрокоманды/предикаты, если потребуется.

Поле "аргумент" интерпретируется в зависимости от опкода:
- LOAD_IMM/ADD_IMM/... -- непосредственное значение (signed 32-bit);
- LOAD_MEM/STORE_MEM/... -- адрес ячейки в памяти данных;
- JMP/JMP_T -- адрес команды (тоже в байтах, т.к. память единая).
"""

import json
import struct
from collections import namedtuple
from enum import IntEnum

from lang.compiler.bytecode import BC

WORD_LEN = 4
"Длина машинного слова в байтах."


# Группы опкодов по числу занимаемых слов (1 vs 2).
# Используется и кодером, и декодером, и ControlUnit'ом для выборки операндов.
ZERO_ARG_OPCODES: frozenset[int] = frozenset({BC.HALT, BC.INT, BC.IRET})

ONE_ARG_OPCODES: frozenset[int] = frozenset(
    {
        BC.LOAD_IMM,
        BC.LOAD_MEM,
        BC.STORE_MEM,
        BC.EQ_IMM,
        BC.NE_IMM,
        BC.LT_IMM,
        BC.LE_IMM,
        BC.GT_IMM,
        BC.GE_IMM,
        BC.ADD_IMM,
        BC.SUB_IMM,
        BC.MUL_IMM,
        BC.DIV_IMM,
        BC.MOD_IMM,
        BC.EQ_MEM,
        BC.NE_MEM,
        BC.LT_MEM,
        BC.LE_MEM,
        BC.GT_MEM,
        BC.GE_MEM,
        BC.ADD_MEM,
        BC.SUB_MEM,
        BC.MUL_MEM,
        BC.DIV_MEM,
        BC.MOD_MEM,
        BC.AND_IMM,
        BC.AND_MEM,
        BC.OR_IMM,
        BC.OR_MEM,
        BC.ASL_IMM,
        BC.ASL_MEM,
        BC.ASR_IMM,
        BC.ASR_MEM,
        BC.LSR_IMM,
        BC.LSR_MEM,
        BC.JMP,
        BC.JMP_T,
        BC.STORE_IND_MEM,
        BC.LOAD_IND_MEM,
    }
)


class AluOp(IntEnum):
    """Микрокоманды ALU. ControlUnit поднимает соответствующий сигнал в зависимости
    от декодированного опкода. Все операции работают над парой (acc, arg), где arg
    -- либо непосредственное значение, либо значение из памяти по адресу."""

    PASS_ARG = 0  # acc <- arg                (LOAD_IMM / LOAD_MEM)
    ADD = 1  # acc <- acc + arg
    SUB = 2  # acc <- acc - arg
    MUL = 3  # acc <- acc * arg
    DIV = 4  # acc <- acc // arg
    MOD = 5  # acc <- acc % arg
    AND = 6  # acc <- acc & arg
    OR = 7  # acc <- acc | arg
    ASL = 8  # acc <- (acc << arg) (signed, маска по WORD_LEN)
    ASR = 9  # acc <- acc >> arg   (с расширением знака)
    LSR = 10  # acc <- (acc & mask) >> arg (логический)
    EQ = 11  # acc <- 1 if acc == arg else 0
    NE = 12  # acc <- 1 if acc != arg else 0
    LT = 13  # acc <- 1 if acc <  arg else 0
    LE = 14  # acc <- 1 if acc <= arg else 0
    GT = 15  # acc <- 1 if acc >  arg else 0
    GE = 16  # acc <- 1 if acc >= arg else 0


class ArgSrc(IntEnum):
    """Откуда брать второй операнд для ALU."""

    NONE = 0  # нет аргумента (HALT/INT/IRET)
    IMM = 1  # из слова N+1 (немедленное значение)
    MEM = 2  # из памяти по адресу из слова N+1
    IND_MEM = 3  # из памяти по адресу, лежащему по адресу из слова N+1
    # (двойная косвенность — для автобоксов)


# Декодер: опкод -> (ALU операция, источник аргумента, "пишет ли в память").
# Поле "writes_back" позволяет хардварному декодеру понимать, нужно ли
# поднимать сигнал signal_wr в финальной микроинструкции.
Decoded = namedtuple("Decoded", "alu arg_src writes")

DECODE: dict[int, Decoded] = {
    # --- Зарезервированные управляющие (без ALU) ---
    BC.HALT: Decoded(AluOp.PASS_ARG, ArgSrc.NONE, False),
    BC.INT: Decoded(AluOp.PASS_ARG, ArgSrc.NONE, False),
    BC.IRET: Decoded(AluOp.PASS_ARG, ArgSrc.NONE, False),
    # --- Передача данных ---
    BC.LOAD_IMM: Decoded(AluOp.PASS_ARG, ArgSrc.IMM, False),
    BC.LOAD_MEM: Decoded(AluOp.PASS_ARG, ArgSrc.MEM, False),
    BC.LOAD_IND_MEM: Decoded(AluOp.PASS_ARG, ArgSrc.IND_MEM, False),
    BC.STORE_MEM: Decoded(AluOp.PASS_ARG, ArgSrc.NONE, True),
    BC.STORE_IND_MEM: Decoded(AluOp.PASS_ARG, ArgSrc.IND_MEM, True),
    # --- Арифметика с непосредственными ---
    BC.ADD_IMM: Decoded(AluOp.ADD, ArgSrc.IMM, False),
    BC.SUB_IMM: Decoded(AluOp.SUB, ArgSrc.IMM, False),
    BC.MUL_IMM: Decoded(AluOp.MUL, ArgSrc.IMM, False),
    BC.DIV_IMM: Decoded(AluOp.DIV, ArgSrc.IMM, False),
    BC.MOD_IMM: Decoded(AluOp.MOD, ArgSrc.IMM, False),
    BC.AND_IMM: Decoded(AluOp.AND, ArgSrc.IMM, False),
    BC.OR_IMM: Decoded(AluOp.OR, ArgSrc.IMM, False),
    BC.ASL_IMM: Decoded(AluOp.ASL, ArgSrc.IMM, False),
    BC.ASR_IMM: Decoded(AluOp.ASR, ArgSrc.IMM, False),
    BC.LSR_IMM: Decoded(AluOp.LSR, ArgSrc.IMM, False),
    # --- Арифметика с памятью ---
    BC.ADD_MEM: Decoded(AluOp.ADD, ArgSrc.MEM, False),
    BC.SUB_MEM: Decoded(AluOp.SUB, ArgSrc.MEM, False),
    BC.MUL_MEM: Decoded(AluOp.MUL, ArgSrc.MEM, False),
    BC.DIV_MEM: Decoded(AluOp.DIV, ArgSrc.MEM, False),
    BC.MOD_MEM: Decoded(AluOp.MOD, ArgSrc.MEM, False),
    BC.AND_MEM: Decoded(AluOp.AND, ArgSrc.MEM, False),
    BC.OR_MEM: Decoded(AluOp.OR, ArgSrc.MEM, False),
    BC.ASL_MEM: Decoded(AluOp.ASL, ArgSrc.MEM, False),
    BC.ASR_MEM: Decoded(AluOp.ASR, ArgSrc.MEM, False),
    BC.LSR_MEM: Decoded(AluOp.LSR, ArgSrc.MEM, False),
    # --- Сравнения с непосредственными ---
    BC.EQ_IMM: Decoded(AluOp.EQ, ArgSrc.IMM, False),
    BC.NE_IMM: Decoded(AluOp.NE, ArgSrc.IMM, False),
    BC.LT_IMM: Decoded(AluOp.LT, ArgSrc.IMM, False),
    BC.LE_IMM: Decoded(AluOp.LE, ArgSrc.IMM, False),
    BC.GT_IMM: Decoded(AluOp.GT, ArgSrc.IMM, False),
    BC.GE_IMM: Decoded(AluOp.GE, ArgSrc.IMM, False),
    # --- Сравнения с памятью ---
    BC.EQ_MEM: Decoded(AluOp.EQ, ArgSrc.MEM, False),
    BC.NE_MEM: Decoded(AluOp.NE, ArgSrc.MEM, False),
    BC.LT_MEM: Decoded(AluOp.LT, ArgSrc.MEM, False),
    BC.LE_MEM: Decoded(AluOp.LE, ArgSrc.MEM, False),
    BC.GT_MEM: Decoded(AluOp.GT, ArgSrc.MEM, False),
    BC.GE_MEM: Decoded(AluOp.GE, ArgSrc.MEM, False),
    # --- Переходы (PC-управление) ---
    BC.JMP: Decoded(AluOp.PASS_ARG, ArgSrc.IMM, False),
    BC.JMP_T: Decoded(AluOp.PASS_ARG, ArgSrc.IMM, False),
}


def opcode_words(opcode: int) -> int:
    """Сколько 32-битных слов занимает инструкция в памяти (1 или 2)."""
    if opcode in ZERO_ARG_OPCODES:
        return 1
    if opcode in ONE_ARG_OPCODES:
        return 2
    raise ValueError(f"unknown opcode: {opcode}")


def encode_instr(opcode: int, arg: int | None) -> bytes:
    """Закодировать одну инструкцию в 4 или 8 байт.

    Слово опкода: младшие 16 бит = код BC, старшие 16 -- ноль (зарезервировано).
    Слово аргумента (если есть): полностью занимает 32 бита (signed).
    """
    assert opcode in DECODE, f"unknown opcode: {opcode}"
    head = struct.pack("<I", opcode & 0xFFFF)
    if opcode in ZERO_ARG_OPCODES:
        assert arg is None or arg == 0, f"{BC(opcode).name} must have no argument"
        return head
    assert arg is not None, f"{BC(opcode).name} requires an argument"
    tail = struct.pack("<i", arg) if arg < 0 else struct.pack("<I", arg & 4294967295)
    return head + tail


def decode_word(word: int) -> int:
    """Извлечь опкод из слова, лежащего по адресу PC."""
    return word & 0xFFFF


def iter_program(image: bytes, code_start: int, stop_at_halt: bool = False):
    """Итератор по командам в образе памяти, начиная с code_start.

    Возвращает кортежи (address_in_bytes, opcode, arg | None, mnemonic_str)
    до конца образа (или до первой HALT, если `stop_at_halt=True`).

    Поскольку в одном образе обычно несколько units (main, k_apply, defun'ы,
    ISR), каждый из которых может иметь свой HALT, по умолчанию итератор
    проходит весь образ.

    Используется только для дампа / отладки; ControlUnit при исполнении делает
    выборку по PC из единого пространства памяти.
    """
    pc = code_start
    while pc + WORD_LEN <= len(image):
        word = struct.unpack("<i", image[pc : pc + WORD_LEN])[0]
        opcode = decode_word(word)
        if opcode not in DECODE:
            return
        if opcode in ZERO_ARG_OPCODES:
            yield pc, opcode, None, BC(opcode).name
            pc += WORD_LEN
            if stop_at_halt and opcode == BC.HALT:
                return
        else:
            if pc + 2 * WORD_LEN > len(image):
                return
            arg = struct.unpack("<i", image[pc + WORD_LEN : pc + 2 * WORD_LEN])[0]
            yield pc, opcode, arg, f"{BC(opcode).name} {arg}"
            pc += 2 * WORD_LEN


def to_hex(image: bytes, code_start: int) -> str:
    """Текстовый дамп команд в формате:

        <address_hex> - <HEXCODE> - <mnemonic>

    Например:
        00000040 - 00000001 0000007B - LOAD_IMM 123
        00000048 - 00000014 00000100 - JMP 256
        00000050 - 00000000          - HALT
    """
    lines = []
    for pc, opcode, arg, mnemonic in iter_program(image, code_start):
        head_hex = f"{opcode & 0xFFFF:08X}"
        if arg is None:
            hex_code = f"{head_hex}         "
        else:
            arg32 = arg & 0xFFFFFFFF
            hex_code = f"{head_hex} {arg32:08X}"
        lines.append(f"{pc:08X} - {hex_code} - {mnemonic}")
    return "\n".join(lines)


def write_json(filename: str, image: bytes, code_start: int) -> None:
    """Дамп программы в JSON.

    Формат: список объектов, по одному на инструкцию:
        {"address": <int>, "opcode": "<NAME>", "arg": <int|null>, "hex": "<HEXCODE>"}
    Один объект на строку (читается людьми, легко diff'ится).
    """
    items = []
    for pc, opcode, arg, _ in iter_program(image, code_start):
        items.append(
            json.dumps(
                {
                    "address": pc,
                    "opcode": BC(opcode).name,
                    "arg": arg,
                    "hex": (
                        f"{opcode & 0xFFFF:08X}"
                        if arg is None
                        else f"{opcode & 0xFFFF:08X} {arg & 0xFFFFFFFF:08X}"
                    ),
                }
            )
        )
    with open(filename, "w", encoding="utf-8") as f:
        f.write("[\n " + ",\n ".join(items) + "\n]")
