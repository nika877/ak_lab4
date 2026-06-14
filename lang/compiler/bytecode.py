
from dataclasses import dataclass, field

import lang.parser.qualname


class BC:
    HALT = 0
    LOAD_IMM = 1
    LOAD_MEM = 2
    STORE_MEM = 3
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
    INT_PRINT = 22
    STORE_IND_MEM = 60
    LOAD_IND_MEM = 70
    DIV_MEM = 123
    MOD_IMM = 321
    MOD_MEM = 333


def iter_bytecode(bc: list[int]):
    i = 0
    while i < len(bc):
        match bc[i]:
            case (
                BC.HALT |
                BC.INT_PRINT
            ):
                yield i, bc[i], tuple()
            case (
                BC.ADD_IMM |
                BC.LOAD_IMM |
                BC.LOAD_MEM |
                BC.STORE_MEM |
                BC.EQ_IMM |
                BC.NE_IMM |
                BC.LT_IMM |
                BC.LE_IMM |
                BC.GT_IMM |
                BC.GE_IMM |
                BC.SUB_IMM |
                BC.MUL_IMM |
                BC.EQ_MEM |
                BC.NE_MEM |
                BC.LT_MEM |
                BC.LE_MEM |
                BC.GT_MEM |
                BC.GE_MEM |
                BC.SUB_MEM |
                BC.ADD_MEM |
                BC.MUL_MEM |
                BC.DIV_MEM |
                BC.JMP |
                BC.JMP_T |
                BC.STORE_IND_MEM |
                BC.LOAD_IND_MEM |
                BC.MOD_IMM |
                BC.MOD_MEM
            ):
                yield i, bc[i], (bc[i+1],)
                i += 1
            case x:
                raise Exception(x)

        i += 1


@dataclass(slots=True)
class IncompleteJmpIndex:
    i: int
    path: lang.parser.qualname.TreePath


@dataclass(slots=True)
class BytecodeUnit:
    path: lang.parser.qualname.TreePath
    bytecode: list[int] = field(default_factory=list)
    incomplete_indicies: list[IncompleteJmpIndex] = field(default_factory=list)
