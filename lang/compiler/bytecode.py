"""Опкоды байткода, единицы кода и доступ к памяти по словам."""

import struct
from dataclasses import dataclass, field
from enum import IntEnum

import lang.parser.qualname


class BC(IntEnum):
    """Коды операций виртуальной машины (опкоды).

    Каждая команда — одно или два 32-битных слова в памяти.
    Архитектура acc: все вычисления идут через аккумулятор.
    """

    HALT = 0  # останов
    LOAD_IMM = 1  # acc ← константа
    LOAD_MEM = 2  # acc ← mem[адрес]
    STORE_MEM = 3  # mem[адрес] ← acc
    EQ_IMM = 4
    NE_IMM = 5
    LT_IMM = 6
    LE_IMM = 7
    GT_IMM = 8
    GE_IMM = 9
    ADD_IMM = 30
    SUB_IMM = 10
    MUL_IMM = 11
    EQ_MEM = 12
    NE_MEM = 13
    LT_MEM = 14
    LE_MEM = 15
    GT_MEM = 16
    GE_MEM = 17
    ADD_MEM = 40
    SUB_MEM = 18
    MUL_MEM = 19
    JMP = 20
    JMP_T = 21
    INT = 22
    IRET = 23
    STORE_IND_MEM = 60  # mem[mem[адрес]] ← acc (для автобоксинга)
    LOAD_IND_MEM = 70  # acc ← mem[mem[адрес]]
    DIV_MEM = 123
    DIV_IMM = 124
    MOD_IMM = 321
    MOD_MEM = 333
    AND_IMM = 334
    AND_MEM = 335
    OR_IMM = 336
    OR_MEM = 337
    ASL_IMM = 338
    ASL_MEM = 339
    ASR_IMM = 340
    ASR_MEM = 341
    LSR_IMM = 342
    LSR_MEM = 343


def iter_bytecode(bc: list[int]):
    """Обход списка опкодов: (индекс, опкод, кортеж аргументов)."""
    i = 0
    while i < len(bc):
        match bc[i]:
            case BC.HALT | BC.INT | BC.IRET:
                yield i, bc[i], ()
            case (
                BC.ADD_IMM
                | BC.LOAD_IMM
                | BC.LOAD_MEM
                | BC.STORE_MEM
                | BC.EQ_IMM
                | BC.NE_IMM
                | BC.LT_IMM
                | BC.LE_IMM
                | BC.GT_IMM
                | BC.GE_IMM
                | BC.SUB_IMM
                | BC.MUL_IMM
                | BC.EQ_MEM
                | BC.NE_MEM
                | BC.LT_MEM
                | BC.LE_MEM
                | BC.GT_MEM
                | BC.GE_MEM
                | BC.SUB_MEM
                | BC.ADD_MEM
                | BC.MUL_MEM
                | BC.DIV_MEM
                | BC.JMP
                | BC.JMP_T
                | BC.STORE_IND_MEM
                | BC.LOAD_IND_MEM
                | BC.MOD_IMM
                | BC.MOD_MEM
                | BC.DIV_IMM
                | BC.AND_IMM
                | BC.AND_MEM
                | BC.OR_IMM
                | BC.OR_MEM
                | BC.ASL_IMM
                | BC.ASL_MEM
                | BC.ASR_IMM
                | BC.ASR_MEM
                | BC.LSR_IMM
                | BC.LSR_MEM
            ):
                yield i, bc[i], (bc[i + 1],)
                i += 1
            case x:
                raise Exception(x)

        i += 1


@dataclass(slots=True)
class IncompleteJmpIndex:
    """Место в коде, где JMP ещё не знает целевой адрес (заполняется позже)."""

    i: int
    path: lang.parser.qualname.TreePath


@dataclass(slots=True)
class BytecodeUnit:
    """Один фрагмент байткода: функция, main, обработчик прерывания и т.д."""

    path: lang.parser.qualname.TreePath
    bytecode: list[int] = field(default_factory=list)
    incomplete_indicies: list[IncompleteJmpIndex] = field(default_factory=list)


class WordMemory:
    """Байт-адресуемая память с доступом по 32-битным словам (little-endian).

    Это единая абстракция для рантайма и аппаратной модели: внутри `bytearray`,
    снаружи -- доступ к 32-битным signed-int словам через `mem[addr]`. Запись
    усекается до signed int32, как и в железе при переполнении.

    Используется:
      - `lang.runtime.interpret` -- для исполнения байткода в программном
         режиме;
      - `lang.machine.DataPath` -- как тракт памяти аппаратной модели.
    """

    inner: bytearray
    word_len: int

    def __init__(self, inner: bytes, word_len: int):
        self.inner = bytearray(inner)
        self.word_len = word_len

    def __getitem__(self, key: int) -> int:
        return struct.unpack("<i", self.inner[key : key + self.word_len])[0]

    def __setitem__(self, key: int, value: int) -> None:
        v = value & 0xFFFFFFFF
        if v & 0x80000000:
            v -= 0x100000000
        self.inner[key : key + self.word_len] = struct.pack("<i", v)

    def __len__(self) -> int:
        return len(self.inner)
