from lang.compiler import CompilationResult, BC
from lang.compiler import Compiler
from lang.compiler.inferrer import infer
from lang.compiler.memory import Memory
from lang.formatter import print_bytecode
from lang.lexer import tokenize
from lang.parser import parse
from lang.parser.step_04_assign_qualnames import VirtualToken
#from lang.formatter import print_bytecode, print_tree, print_typed_expression


def interpret(code: list[int], entry_point: int):
    code.extend([0]*10000)
    bc = code
    ip = entry_point
    acc = 0
    log = []
    try:
        while True:
            match bc[ip]:
                case BC.HALT:
                    log.append(f"[{ip:04}] HALT")
                    return acc, log

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

                case unknown:
                    raise Exception(f"unknown instruction: {unknown} at {ip}")

            ip += 1
    except IndexError:
        log.append("[no heap]")
        return -1, log

code = """
(defun is_palindrome_rec (n rev original)
  (if (== n 0)
      (== rev original)
      (is_palindrome_rec (/ n 10) (+ (* rev 10) (- n (* (/ n 10) 10))) original)))

(defun loop_j (i j current_max)
  (if (< j 100)
      current_max
      (if (> (* i j) current_max)
          (if (is_palindrome_rec (* i j) 0 (* i j))
              (loop_j i (- j 1) (* i j))
              (loop_j i (- j 1) current_max))
          (loop_j i (- j 1) current_max))))

(defun loop_i (i current_max)
  (if (< i 100)
      (print current_max)
      (loop_i (- i 1) (loop_j i i current_max))))

(print (loop_i 999 0))
"""
code = """
(defun test (x) (
    (lambda (y)
        ((lambda (z)
            (print (+ z x))
        ) 1)
    ) 2)
)
(test 3)
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
        print(path, " = ", token.qualname.path)

inferred = infer(res)

for inf in inferred.all_inferred:
    print(inf.qualname.path, " = ", inf.lang_type)

comp = Compiler.compile(inferred)

print_bytecode(comp.bytecode, comp.meta)

result, log = interpret(comp.bytecode, comp.entry_point)
print('\n'.join(log))
print("RESULT:", result)
