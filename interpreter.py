from lang.compiler import CompilationResult, BC
from lang.compiler import Compiler
from lang.compiler.inferrer import infer
from lang.compiler.memory import Memory
from lang.formatter import print_bytecode
from lang.lexer import tokenize
from lang.parser import parse
from lang.parser.step_04_assign_qualnames import VirtualToken
#from lang.formatter import print_bytecode, print_tree, print_typed_expression


def interpret(code: list[int], entry_point: int, auto_print_log=False):
    code.extend([0]*100000)
    bc = code
    ip = entry_point
    acc = 0
    log = []
    last_printed_idx = 0
    try:
        while True:
            if auto_print_log:
                print("\n".join(log[last_printed_idx:]))
                last_printed_idx = len(log)

            match bc[ip]:
                case BC.HALT:
                    log.append(f"[{ip:04}] HALT")
                    break

                case BC.LOAD_IMM:
                    log.append(f"[{ip:04}] acc = {bc[ip+1]}")
                    acc = bc[ip+1]
                    ip += 1

                case BC.LOAD_MEM:
                    log.append(f"[{ip:04}] acc = mem[{bc[ip+1]}] -> acc = {bc[bc[ip+1]]}")
                    acc = bc[bc[ip+1]]
                    ip += 1

                case BC.STORE_MEM:
                    log.append(f"[{ip:04}] mem[{bc[ip+1]}] = acc -> mem[{bc[ip+1]}] = {acc}")
                    bc[bc[ip+1]] = acc
                    ip += 1

                case BC.EQ_IMM:
                    log.append(f"[{ip:04}] acc = acc == {bc[ip+1]} -> acc = {[0, 1][acc == bc[ip+1]]}")
                    acc = [0, 1][acc == bc[ip+1]]
                    ip += 1

                case BC.NE_IMM:
                    log.append(f"[{ip:04}] acc = acc != {bc[ip+1]} -> acc = {[0, 1][acc != bc[ip+1]]}")
                    acc = [0, 1][acc != bc[ip+1]]
                    ip += 1

                case BC.LT_IMM:
                    log.append(f"[{ip:04}] acc = acc < {bc[ip+1]} -> acc = {[0, 1][acc < bc[ip+1]]}")
                    acc = [0, 1][acc < bc[ip+1]]
                    ip += 1

                case BC.LE_IMM:
                    log.append(f"[{ip:04}] acc = acc <= {bc[ip+1]} -> acc = {[0, 1][acc <= bc[ip+1]]}")
                    acc = [0, 1][acc <= bc[ip+1]]
                    ip += 1

                case BC.GT_IMM:
                    log.append(f"[{ip:04}] acc = acc > {bc[ip+1]} -> acc = {[0, 1][acc > bc[ip+1]]}")
                    acc = [0, 1][acc > bc[ip+1]]
                    ip += 1

                case BC.GE_IMM:
                    log.append(f"[{ip:04}] acc = acc >= {bc[ip+1]} -> acc = {[0, 1][acc >= bc[ip+1]]}")
                    acc = [0, 1][acc >= bc[ip+1]]
                    ip += 1

                case BC.ADD_IMM:
                    log.append(f"[{ip:04}] acc = acc + {bc[ip+1]} -> acc = {acc + bc[ip+1]}")
                    acc = acc + bc[ip+1]
                    ip += 1

                case BC.SUB_IMM:
                    log.append(f"[{ip:04}] acc = acc - {bc[ip+1]} -> acc = {acc - bc[ip+1]}")
                    acc = acc - bc[ip+1]
                    ip += 1

                case BC.MUL_IMM:
                    log.append(f"[{ip:04}] acc = acc * {bc[ip+1]} -> acc = {acc * bc[ip+1]}")
                    acc = acc * bc[ip+1]
                    ip += 1

                case BC.EQ_MEM:
                    log.append(f"[{ip:04}] acc = acc == mem[{bc[ip+1]}] -> acc = {[0, 1][acc == bc[bc[ip+1]]]}")
                    acc = [0, 1][acc == bc[bc[ip+1]]]
                    ip += 1

                case BC.NE_MEM:
                    log.append(f"[{ip:04}] acc = acc != mem[{bc[ip+1]}] -> acc = {[0, 1][acc != bc[bc[ip+1]]]}")
                    acc = [0, 1][acc != bc[bc[ip+1]]]
                    ip += 1

                case BC.LT_MEM:
                    log.append(f"[{ip:04}] acc = acc < mem[{bc[ip+1]}] -> acc = {[0, 1][acc < bc[bc[ip+1]]]}")
                    acc = [0, 1][acc < bc[bc[ip+1]]]
                    ip += 1

                case BC.LE_MEM:
                    log.append(f"[{ip:04}] acc = acc <= mem[{bc[ip+1]}] -> acc = {[0, 1][acc <= bc[bc[ip+1]]]}")
                    acc = [0, 1][acc <= bc[bc[ip+1]]]
                    ip += 1

                case BC.GT_MEM:
                    log.append(f"[{ip:04}] acc = acc > mem[{bc[ip+1]}] -> acc = {[0, 1][acc > bc[bc[ip+1]]]}")
                    acc = [0, 1][acc > bc[bc[ip+1]]]
                    ip += 1

                case BC.GE_MEM:
                    log.append(f"[{ip:04}] acc = acc >= mem[{bc[ip+1]}] -> acc = {[0, 1][acc >= bc[bc[ip+1]]]}")
                    acc = [0, 1][acc >= bc[bc[ip+1]]]
                    ip += 1

                case BC.ADD_MEM:
                    log.append(f"[{ip:04}] acc = acc + mem[{bc[ip+1]}] -> acc = {acc + bc[bc[ip+1]]}")
                    acc = acc + bc[bc[ip+1]]
                    ip += 1

                case BC.SUB_MEM:
                    log.append(f"[{ip:04}] acc = acc - mem[{bc[ip+1]}] -> acc = {acc - bc[bc[ip+1]]}")
                    acc = acc - bc[bc[ip+1]]
                    ip += 1

                case BC.MUL_MEM:
                    log.append(f"[{ip:04}] acc = acc * mem[{bc[ip+1]}] -> acc = {acc * bc[bc[ip+1]]}")
                    acc = acc * bc[bc[ip+1]]
                    ip += 1

                case BC.DIV_MEM:
                    log.append(f"[{ip:04}] acc = acc / mem[{bc[ip+1]}] -> acc = {acc // bc[bc[ip+1]]}")
                    acc = acc // bc[bc[ip+1]]
                    ip += 1

                case BC.JMP:
                    log.append(f"[{ip:04}] ip = {bc[ip+1]}")
                    ip = bc[ip+1]
                    continue

                case BC.JMP_T:
                    if acc:
                        log.append(f"[{ip:04}] ip = {bc[ip+1]}")
                        ip = bc[ip+1]
                        continue
                    else:
                        ip += 1

                case BC.INT_PRINT:
                    log.append(f"[{ip:04}] [print]")
                    print(acc)

                case BC.STORE_IND_MEM:
                    log.append(f"[{ip:04}] mem[mem[{bc[ip+1]}]] = acc -> mem[mem[{bc[ip+1]}]] = {acc}")
                    bc[bc[bc[ip+1]]] = acc
                    ip += 1

                case BC.LOAD_IND_MEM:
                    log.append(f"[{ip:04}] acc = mem[mem[{bc[ip+1]}]] -> acc = {bc[bc[bc[ip+1]]]}")
                    acc = bc[bc[bc[ip+1]]]
                    ip += 1

                case BC.MOD_MEM:
                    log.append(f"[{ip:04}] acc = acc mod mem[{bc[ip+1]}] -> acc = {acc % bc[bc[ip+1]]}")
                    acc = acc % bc[bc[ip+1]]
                    ip += 1

                case BC.MOD_IMM:
                    log.append(f"[{ip:04}] acc = acc mod {bc[ip+1]} -> acc = {acc % bc[ip+1]}")
                    acc = acc % bc[ip+1]
                    ip += 1

                case unknown:
                    raise Exception(f"unknown instruction: {unknown} at {ip}")

            ip += 1
    except IndexError:
        log.append("[no heap]")
        acc = -1

    if auto_print_log:
        print("\n".join(log[last_printed_idx:]))

    return acc, log

code = """
(defun solve-euler-1 (n acc)
  (if (== n 0)
      acc
      (solve-euler-1 (- n 1)
                     (+ acc (if (or (== (mod n 3) 0)
                                    (== (mod n 5) 0))
                                n
                                0)))))

(print (solve-euler-1 999 0))
"""
#code = """
#(print (+ 1 2))
#"""
from lang.parser import parse
from pprint import pprint

res = parse(tokenize(code))

for path, token in res.all_tokens.items():
    if isinstance(token, VirtualToken):
        print("VIRT", " = ", path)
    else:
        print(token.source, " = ", token.qualname.path)

inferred = infer(res)

for inf in inferred.all_inferred:
    print(inf.qualname.path, " = ", inf.lang_type)

comp = Compiler.compile(inferred)

print_bytecode(comp.bytecode, comp.meta)

result, log = interpret(comp.bytecode, comp.entry_point, auto_print_log=False)
#print('\n'.join(log))
print("ACC AFTER HALT:", result)
