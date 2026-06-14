from lang.compiler import CompilationResultMeta, Memory, BC

def _unit_start(i: int, meta: CompilationResultMeta):
    if i < len(meta.memory.slots):
        return None

    i_cnt = len(meta.memory.slots)
    for unit in meta.processed_units:
        if i == i_cnt:
            return unit.path
        i_cnt += len(unit.bytecode)


def _print_bytecode(bc: list[int], meta: CompilationResultMeta, offset = 0, padding = 4):
    i = offset
    print("memory:")
    while i < len(bc):
        if start := _unit_start(i, meta):
            print(f"\n{start}:")

        print(f"{' '*padding}{i:04} = {bc[i]:04}  |  ", end=' ')
        if i < len(meta.memory.slots):
            print(f"({meta.memory.slots[i].path})")
        else:
            match bc[i]:
                case BC.HALT:
                    print("HALT")
                case BC.LOAD_IMM:
                    if s := _unit_start(bc[i + 1], meta):
                        print(f"LOAD #{bc[i+1]} (start of {s})")
                    else:
                        print(f"LOAD #{bc[i+1]}")
                    i += 1
                case BC.LOAD_MEM:
                    print(f"LOAD [{bc[i+1]}] ({meta.memory.slots[bc[i+1]].path})")
                    i += 1
                case BC.STORE_MEM:
                    print(f"STORE [{bc[i+1]}] ({meta.memory.slots[bc[i+1]].path})")
                    i += 1
                case BC.EQ_IMM:
                    print(f"EQ #{bc[i+1]}")
                    i += 1
                case BC.NE_IMM:
                    print(f"NE #{bc[i+1]}")
                    i += 1
                case BC.LT_IMM:
                    print(f"LT #{bc[i+1]}")
                    i += 1
                case BC.LE_IMM:
                    print(f"LE #{bc[i+1]}")
                    i += 1
                case BC.GT_IMM:
                    print(f"GT #{bc[i+1]}")
                    i += 1
                case BC.GE_IMM:
                    print(f"GE #{bc[i+1]}")
                    i += 1
                case BC.SUB_IMM:
                    print(f"SUB #{bc[i+1]}")
                    i += 1
                case BC.ADD_IMM:
                    print(f"ADD #{bc[i+1]}")
                    i += 1
                case BC.MUL_IMM:
                    print(f"MUL #{bc[i+1]}")
                    i += 1
                case BC.EQ_MEM:
                    print(f"EQ [{bc[i+1]}] ({meta.memory.slots[bc[i+1]].path})")
                    i += 1
                case BC.NE_MEM:
                    print(f"NE [{bc[i+1]}] ({meta.memory.slots[bc[i+1]].path})")
                    i += 1
                case BC.LT_MEM:
                    print(f"LT [{bc[i+1]}] ({meta.memory.slots[bc[i+1]].path})")
                    i += 1
                case BC.LE_MEM:
                    print(f"LE [{bc[i+1]}] ({meta.memory.slots[bc[i+1]].path})")
                    i += 1
                case BC.GT_MEM:
                    print(f"GT [{bc[i+1]}] ({meta.memory.slots[bc[i+1]].path})")
                    i += 1
                case BC.GE_MEM:
                    print(f"GE [{bc[i+1]}] ({meta.memory.slots[bc[i+1]].path})")
                    i += 1
                case BC.SUB_MEM:
                    print(f"SUB [{bc[i+1]}] ({meta.memory.slots[bc[i+1]].path})")
                    i += 1
                case BC.ADD_MEM:
                    print(f"ADD [{bc[i+1]}] ({meta.memory.slots[bc[i+1]].path})")
                    i += 1
                case BC.MUL_MEM:
                    print(f"MUL [{bc[i+1]}] ({meta.memory.slots[bc[i+1]].path})")
                    i += 1
                case BC.DIV_MEM:
                    print(f"DIV [{bc[i+1]}] ({meta.memory.slots[bc[i+1]].path})")
                    i += 1
                case BC.JMP:
                    if s := _unit_start(bc[i + 1], meta):
                        print(f"JMP #{bc[i+1]} (start of {s})")
                    else:
                        print(f"JMP #{bc[i+1]}")
                    i += 1
                case BC.JMP_T:
                    if s := _unit_start(bc[i + 1], meta):
                        print(f"JMP_T #{bc[i+1]} (start of {s})")
                    else:
                        print(f"JMP_T #{bc[i+1]}")
                    i += 1
                case BC.INT_PRINT:
                    print(f"INT (PRINT)")
                case BC.STORE_IND_MEM:
                    print(f"STORE INDIRECT [{bc[i+1]}] (via {meta.memory.slots[bc[i+1]].path})")
                    i += 1
                case BC.LOAD_IND_MEM:
                    print(f"LOAD INDIRECT [{bc[i+1]}] (via {meta.memory.slots[bc[i+1]].path})")
                    i += 1
                case _:
                    print(f"?")

        i += 1


def print_bytecode(bc: list[int], meta: CompilationResultMeta):
    _print_bytecode(bc, meta)
