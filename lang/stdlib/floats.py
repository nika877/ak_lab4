"""Встроенные операции над FLOAT (32-битные числа с плавающей точкой)."""

import lang.compiler as compiler
from lang.compiler.bytecode import BC
from lang.lang_type import (
    FunctionLanguageType,
    PrimitiveLanguageType,
)
from lang.parser.qualname import (
    BuiltinSymbol,
    LambdaEmitter,
    TreePathEntry,
)


def builtin_to_string_float():
    def emit_bytecode(unit, slots, k, *args):
        bytecode = unit.bytecode

        # 1. Init and allocate buffer (32 words)
        bytecode.extend(
            [
                BC.LOAD_MEM,
                args[0],
                BC.STORE_MEM,
                slots[0],  # INPUT_VAL
                BC.LOAD_IMM,
                0,
                BC.STORE_MEM,
                slots[4],  # DIGIT_COUNT = 0
                # IS_NEG = (INPUT_VAL >> 31) & 1
                BC.LOAD_MEM,
                slots[0],
                BC.LSR_IMM,
                31,
                BC.AND_IMM,
                1,
                BC.STORE_MEM,
                slots[1],
                # START_PTR = HEAP; HEAP += 32; WRITE_PTR = START_PTR + 31
                BC.LOAD_MEM,
                compiler.Memory.HEAP,
                BC.STORE_MEM,
                slots[3],
                BC.ADD_IMM,
                32 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                compiler.Memory.HEAP,
                BC.LOAD_MEM,
                slots[3],
                BC.ADD_IMM,
                31 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[2],
            ]
        )

        # 2. Decode IEEE 754 (Exponent -> TMP_BIT temp, Mantissa -> INT_PART)
        bytecode.extend(
            [
                # TMP_BIT(8) = EXPONENT = (INPUT_VAL >> 23) & 0xFF
                BC.LOAD_MEM,
                slots[0],
                BC.LSR_IMM,
                23,
                BC.AND_IMM,
                0xFF,
                BC.STORE_MEM,
                slots[8],
                # INT_PART(5) = MANTISSA = INPUT_VAL & 0x7FFFFF
                BC.LOAD_MEM,
                slots[0],
                BC.AND_IMM,
                0x7FFFFF,
                BC.STORE_MEM,
                slots[5],
            ]
        )

        # Check for zero (EXP == 0)
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[8],
                BC.EQ_IMM,
                0,
                BC.JMP_T,
                -1,  # [PATCH 1] jump to zero handling
            ]
        )
        patch_zero = len(bytecode) - 1

        # Normal number: add implicit leading bit
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[5],
                BC.OR_IMM,
                0x800000,
                BC.STORE_MEM,
                slots[5],
            ]
        )

        # Compute SHIFT = 150 - EXPONENT
        bytecode.extend(
            [
                BC.LOAD_IMM,
                150,
                BC.SUB_MEM,
                slots[8],
                BC.STORE_MEM,
                slots[7],  # SHIFT (7)
                BC.LOAD_IMM,
                0,
                BC.STORE_MEM,
                slots[6],  # FRAC_PART (6) = 0
            ]
        )

        # Branch based on SHIFT
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[7],
                BC.LT_IMM,
                0,
                BC.JMP_T,
                -1,  # [PATCH 2] -> LSHIFT_LOOP
                BC.LOAD_MEM,
                slots[7],
                BC.GT_IMM,
                0,
                BC.JMP_T,
                -1,  # [PATCH 3] -> RSHIFT_LOOP
                BC.JMP,
                -1,  # [PATCH 4] -> END_SHIFTS (SHIFT == 0)
            ]
        )
        patch_lt = len(bytecode) - 9
        patch_gt = len(bytecode) - 3
        patch_eq = len(bytecode) - 1

        # --- ZERO BLOCK ---
        bytecode[patch_zero] = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode.extend(
            [
                BC.LOAD_IMM,
                0,
                BC.STORE_MEM,
                slots[5],  # INT_PART = 0
                BC.STORE_MEM,
                slots[6],  # FRAC_PART = 0
                BC.JMP,
                -1,  # [PATCH 5] -> END_SHIFTS
            ]
        )
        patch_force_zero_jmp = len(bytecode) - 1

        # --- LEFT SHIFT (numbers >= 2^23) ---
        lbl_lshift = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_lt] = lbl_lshift
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[7],
                BC.EQ_IMM,
                0,
                BC.JMP_T,
                -1,  # [PATCH 6] -> END_SHIFTS
            ]
        )
        patch_lshift_end = len(bytecode) - 1

        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[5],
                BC.MUL_IMM,
                2,  # INT_PART *= 2
                BC.STORE_MEM,
                slots[5],
                BC.LOAD_MEM,
                slots[7],
                BC.ADD_IMM,
                1,
                BC.STORE_MEM,
                slots[7],
                BC.JMP,
                lbl_lshift,
            ]
        )

        # --- RIGHT SHIFT (numbers with fractional part) ---
        lbl_rshift = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_gt] = lbl_rshift
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[7],
                BC.EQ_IMM,
                0,
                BC.JMP_T,
                -1,  # [PATCH 7] -> END_SHIFTS
            ]
        )
        patch_rshift_end = len(bytecode) - 1

        bytecode.extend(
            [
                # TMP_BIT = INT_PART % 2
                BC.LOAD_MEM,
                slots[5],
                BC.MOD_IMM,
                2,
                BC.STORE_MEM,
                slots[8],
                # INT_PART /= 2
                BC.LOAD_MEM,
                slots[5],
                BC.DIV_IMM,
                2,
                BC.STORE_MEM,
                slots[5],
                # FRAC_PART /= 2
                BC.LOAD_MEM,
                slots[6],
                BC.DIV_IMM,
                2,
                BC.STORE_MEM,
                slots[6],
                # FRAC_PART += TMP_BIT * 50000 (fixed point for 5 digits)
                BC.LOAD_MEM,
                slots[8],
                BC.MUL_IMM,
                50000,
                BC.ADD_MEM,
                slots[6],
                BC.STORE_MEM,
                slots[6],
                # SHIFT--
                BC.LOAD_MEM,
                slots[7],
                BC.SUB_IMM,
                1,
                BC.STORE_MEM,
                slots[7],
                BC.JMP,
                lbl_rshift,
            ]
        )

        # --- END SHIFTS ---
        lbl_end_shifts = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_eq] = lbl_end_shifts
        bytecode[patch_force_zero_jmp] = lbl_end_shifts
        bytecode[patch_lshift_end] = lbl_end_shifts
        bytecode[patch_rshift_end] = lbl_end_shifts

        # 3. Generate string from the end
        # Allocate 5 digits for fraction
        bytecode.extend(
            [
                BC.LOAD_IMM,
                5,
                BC.STORE_MEM,
                slots[8],  # Fractional digit counter
            ]
        )

        lbl_frac_loop = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[8],
                BC.EQ_IMM,
                0,
                BC.JMP_T,
                -1,  # [PATCH 8] -> END FRACTION
            ]
        )
        patch_frac_end = len(bytecode) - 1

        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[6],
                BC.MOD_IMM,
                10,
                BC.ADD_IMM,
                48,
                BC.STORE_IND_MEM,
                slots[2],  # *WRITE_PTR = FRAC_PART % 10 + '0'
                BC.LOAD_MEM,
                slots[2],
                BC.SUB_IMM,
                compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[2],  # WRITE_PTR--
                BC.LOAD_MEM,
                slots[6],
                BC.DIV_IMM,
                10,
                BC.STORE_MEM,
                slots[6],  # FRAC_PART /= 10
                BC.LOAD_MEM,
                slots[4],
                BC.ADD_IMM,
                1,
                BC.STORE_MEM,
                slots[4],  # DIGIT_COUNT++
                BC.LOAD_MEM,
                slots[8],
                BC.SUB_IMM,
                1,
                BC.STORE_MEM,
                slots[8],  # Counter--
                BC.JMP,
                lbl_frac_loop,
            ]
        )

        # Decimal point
        lbl_frac_end = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_frac_end] = lbl_frac_end
        bytecode.extend(
            [
                BC.LOAD_IMM,
                46,  # '.'
                BC.STORE_IND_MEM,
                slots[2],
                BC.LOAD_MEM,
                slots[2],
                BC.SUB_IMM,
                compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[2],
                BC.LOAD_MEM,
                slots[4],
                BC.ADD_IMM,
                1,
                BC.STORE_MEM,
                slots[4],
            ]
        )

        # Generate integer part
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[5],
                BC.EQ_IMM,
                0,
                BC.JMP_T,
                -1,  # [PATCH 9] -> "0" exception
            ]
        )
        patch_int_zero = len(bytecode) - 1

        lbl_int_loop = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[5],
                BC.EQ_IMM,
                0,
                BC.JMP_T,
                -1,  # [PATCH 10] -> SIGN
            ]
        )
        patch_int_end = len(bytecode) - 1

        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[5],
                BC.MOD_IMM,
                10,
                BC.ADD_IMM,
                48,
                BC.STORE_IND_MEM,
                slots[2],
                BC.LOAD_MEM,
                slots[2],
                BC.SUB_IMM,
                compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[2],
                BC.LOAD_MEM,
                slots[5],
                BC.DIV_IMM,
                10,
                BC.STORE_MEM,
                slots[5],
                BC.LOAD_MEM,
                slots[4],
                BC.ADD_IMM,
                1,
                BC.STORE_MEM,
                slots[4],
                BC.JMP,
                lbl_int_loop,
            ]
        )

        # If integer part was 0
        lbl_int_zero = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_int_zero] = lbl_int_zero
        bytecode.extend(
            [
                BC.LOAD_IMM,
                48,  # '0'
                BC.STORE_IND_MEM,
                slots[2],
                BC.LOAD_MEM,
                slots[2],
                BC.SUB_IMM,
                compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[2],
                BC.LOAD_MEM,
                slots[4],
                BC.ADD_IMM,
                1,
                BC.STORE_MEM,
                slots[4],
            ]
        )

        # Check sign
        lbl_sign_check = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_int_end] = lbl_sign_check
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[1],
                BC.EQ_IMM,
                0,
                BC.JMP_T,
                -1,  # [PATCH 11] -> FINISH
            ]
        )
        patch_finish = len(bytecode) - 1

        bytecode.extend(
            [
                BC.LOAD_IMM,
                45,  # '-'
                BC.STORE_IND_MEM,
                slots[2],
                BC.LOAD_MEM,
                slots[2],
                BC.SUB_IMM,
                compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[2],
                BC.LOAD_MEM,
                slots[4],
                BC.ADD_IMM,
                1,
                BC.STORE_MEM,
                slots[4],
            ]
        )

        # 4. Finish and CPS continuation
        lbl_finish = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_finish] = lbl_finish
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[4],
                BC.STORE_IND_MEM,
                slots[2],  # *WRITE_PTR = DIGIT_COUNT (Pascal length)
            ]
        )

        compiler.Compiler.emit_write_args_inplace(unit, [[BC.LOAD_MEM, slots[2]]])
        compiler.Compiler.emit_load_k(unit, k)
        compiler.Compiler.emit_apply_k(unit)

    return BuiltinSymbol(
        source="to-string",
        path=TreePathEntry.for_builtin("to-string<float>").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.FLOAT,
                FunctionLanguageType([PrimitiveLanguageType.STRING], typevar_emitter()),
            ],
            PrimitiveLanguageType.VOID,
        ),
        emit_inplace=None,
        emit_lambda=LambdaEmitter(
            slots=[
                "INPUT_VAL",
                "IS_NEG",
                "WRITE_PTR",
                "START_PTR",
                "DIGIT_COUNT",
                "INT_PART",
                "FRAC_PART",
                "SHIFT",
                "TMP_BIT",
            ],
            bytecode_emitter=emit_bytecode,
        ),
    )


def builtin_to_float_unchecked_string():
    """Parse float from string: "3.14" -> 3 (simplified, ignores fraction)"""

    def emit_to_float_bytecode(unit, slots, k, *args):
        bytecode = unit.bytecode

        bytecode.extend(
            [
                BC.LOAD_MEM,
                args[0],
                BC.STORE_MEM,
                slots[0],  # STR_PTR
                BC.LOAD_IND_MEM,
                slots[0],
                BC.STORE_MEM,
                slots[1],  # LEN = *STR_PTR
                BC.LOAD_IMM,
                0,
                BC.STORE_MEM,
                slots[2],  # INT_PART = 0
                BC.STORE_MEM,
                slots[3],  # FRAC_PART = 0
                BC.STORE_MEM,
                slots[4],  # IS_NEG = 0
                BC.STORE_MEM,
                slots[5],  # FRAC_SCALE = 0
                # PTR = STR_PTR + WORD_LEN
                BC.LOAD_MEM,
                slots[0],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[6],
                # END_PTR = PTR + LEN * WORD_LEN
                BC.LOAD_MEM,
                slots[1],
                BC.MUL_IMM,
                compiler.Memory.WORD_LEN,
                BC.ADD_MEM,
                slots[6],
                BC.STORE_MEM,
                slots[7],
            ]
        )

        # Check for empty string
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[6],
                BC.EQ_MEM,
                slots[7],
                BC.JMP_T,
                0,
            ]
        )
        jmp_empty_idx = len(bytecode) - 1

        # Check sign '-'
        bytecode.extend(
            [
                BC.LOAD_IND_MEM,
                slots[6],
                BC.NE_IMM,
                45,
                BC.JMP_T,
                0,
            ]
        )
        jmp_to_int_idx = len(bytecode) - 1

        # If '-', set flag and advance pointer
        bytecode.extend(
            [
                BC.LOAD_IMM,
                1,
                BC.STORE_MEM,
                slots[4],
                BC.LOAD_MEM,
                slots[6],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[6],
            ]
        )

        # Integer part parsing loop
        int_loop_start = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[jmp_to_int_idx] = int_loop_start

        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[6],
                BC.EQ_MEM,
                slots[7],
                BC.JMP_T,
                0,
            ]
        )
        jmp_int_exit_idx = len(bytecode) - 1

        bytecode.extend(
            [
                BC.LOAD_IND_MEM,
                slots[6],
                BC.EQ_IMM,
                46,
                BC.JMP_T,
                0,
            ]
        )
        jmp_frac_start_idx = len(bytecode) - 1

        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[2],
                BC.MUL_IMM,
                10,
                BC.STORE_MEM,
                slots[2],
                BC.LOAD_IND_MEM,
                slots[6],
                BC.SUB_IMM,
                48,
                BC.ADD_MEM,
                slots[2],
                BC.STORE_MEM,
                slots[2],
                BC.LOAD_MEM,
                slots[6],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[6],
                BC.JMP,
                int_loop_start,
            ]
        )

        # Fractional part parsing
        frac_start_label = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[jmp_frac_start_idx] = frac_start_label
        bytecode[jmp_int_exit_idx] = frac_start_label

        # Skip '.'
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[6],
                BC.EQ_MEM,
                slots[7],
                BC.JMP_T,
                0,
            ]
        )
        jmp_final_idx = len(bytecode) - 1

        bytecode.extend(
            [
                BC.LOAD_IND_MEM,
                slots[6],
                BC.NE_IMM,
                46,
                BC.JMP_T,
                0,
            ]
        )
        jmp_not_dot_idx = len(bytecode) - 1

        # Has dot, skip it
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[6],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[6],
                BC.LOAD_IMM,
                1,
                BC.STORE_MEM,
                slots[5],
            ]
        )

        # Fraction loop
        frac_loop_start = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[jmp_not_dot_idx] = frac_loop_start

        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[6],
                BC.EQ_MEM,
                slots[7],
                BC.JMP_T,
                0,
            ]
        )
        jmp_frac_exit_idx = len(bytecode) - 1

        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[3],
                BC.MUL_IMM,
                10,
                BC.STORE_MEM,
                slots[3],
                BC.LOAD_IND_MEM,
                slots[6],
                BC.SUB_IMM,
                48,
                BC.ADD_MEM,
                slots[3],
                BC.STORE_MEM,
                slots[3],
                BC.LOAD_MEM,
                slots[5],
                BC.MUL_IMM,
                10,
                BC.STORE_MEM,
                slots[5],
                BC.LOAD_MEM,
                slots[6],
                BC.ADD_IMM,
                1 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[6],
                BC.JMP,
                frac_loop_start,
            ]
        )

        # Apply sign to INT_PART
        final_label = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[jmp_empty_idx] = final_label
        bytecode[jmp_final_idx] = final_label
        bytecode[jmp_frac_exit_idx] = final_label

        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[4],
                BC.EQ_IMM,
                0,
                BC.JMP_T,
                0,
            ]
        )
        jmp_skip_neg_idx = len(bytecode) - 1

        bytecode.extend(
            [
                BC.LOAD_IMM,
                0,
                BC.SUB_MEM,
                slots[2],
                BC.STORE_MEM,
                slots[2],
            ]
        )

        bytecode[jmp_skip_neg_idx] = len(bytecode) * compiler.Memory.WORD_LEN

        compiler.Compiler.emit_write_args_inplace(unit, [[BC.LOAD_MEM, slots[2]]])
        compiler.Compiler.emit_load_k(unit, k)
        compiler.Compiler.emit_apply_k(unit)

    return BuiltinSymbol(
        source="to-float-unchecked",
        path=TreePathEntry.for_builtin("to-float-unchecked<string>").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.STRING,
                FunctionLanguageType([PrimitiveLanguageType.FLOAT], typevar_emitter()),
            ],
            PrimitiveLanguageType.VOID,
        ),
        emit_inplace=None,
        emit_lambda=LambdaEmitter(
            slots=[
                "STR_PTR",
                "LEN",
                "INT_PART",
                "FRAC_PART",
                "IS_NEG",
                "FRAC_SCALE",
                "PTR",
                "END_PTR",
            ],
            bytecode_emitter=emit_to_float_bytecode,
        ),
    )


def builtin_to_integer_from_float():
    """Convert IEEE 754 float to integer by extracting the integer part."""

    def emit_bytecode(unit, slots, k, *args):
        bytecode = unit.bytecode

        # slots: INPUT(0), SIGN(1), EXP(2), MANT(3), SHIFT(4), RESULT(5)
        bytecode.extend(
            [
                BC.LOAD_MEM,
                args[0],
                BC.STORE_MEM,
                slots[0],
                # SIGN = (INPUT >> 31) & 1
                BC.LOAD_MEM,
                slots[0],
                BC.LSR_IMM,
                31,
                BC.AND_IMM,
                1,
                BC.STORE_MEM,
                slots[1],
                # EXP = (INPUT >> 23) & 0xFF
                BC.LOAD_MEM,
                slots[0],
                BC.LSR_IMM,
                23,
                BC.AND_IMM,
                0xFF,
                BC.STORE_MEM,
                slots[2],
                # MANT = (INPUT & 0x7FFFFF) | 0x800000
                BC.LOAD_MEM,
                slots[0],
                BC.AND_IMM,
                0x7FFFFF,
                BC.OR_IMM,
                0x800000,
                BC.STORE_MEM,
                slots[3],
            ]
        )

        # Check for zero exponent (denormal/zero)
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[2],
                BC.EQ_IMM,
                0,
                BC.JMP_T,
                -1,
            ]
        )
        patch_zero = len(bytecode) - 1

        # SHIFT = 150 - EXP (bias=127, mantissa has 23 bits, so 127+23=150)
        bytecode.extend(
            [
                BC.LOAD_IMM,
                150,
                BC.SUB_MEM,
                slots[2],
                BC.STORE_MEM,
                slots[4],
            ]
        )

        # If SHIFT < 0, shift mantissa left
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[4],
                BC.LT_IMM,
                0,
                BC.JMP_T,
                -1,
            ]
        )
        patch_lshift = len(bytecode) - 1

        # SHIFT >= 0: shift mantissa right
        lbl_rshift = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[4],
                BC.EQ_IMM,
                0,
                BC.JMP_T,
                -1,
            ]
        )
        patch_rshift_end = len(bytecode) - 1
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[3],
                BC.DIV_IMM,
                2,
                BC.STORE_MEM,
                slots[3],
                BC.LOAD_MEM,
                slots[4],
                BC.SUB_IMM,
                1,
                BC.STORE_MEM,
                slots[4],
                BC.JMP,
                lbl_rshift,
            ]
        )

        # Left shift
        lbl_lshift = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_lshift] = lbl_lshift
        bytecode.extend(
            [
                BC.LOAD_IMM,
                0,
                BC.SUB_MEM,
                slots[4],
                BC.STORE_MEM,
                slots[4],
            ]
        )
        lbl_lshift_loop = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[4],
                BC.EQ_IMM,
                0,
                BC.JMP_T,
                -1,
            ]
        )
        patch_lshift_end = len(bytecode) - 1
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[3],
                BC.MUL_IMM,
                2,
                BC.STORE_MEM,
                slots[3],
                BC.LOAD_MEM,
                slots[4],
                BC.SUB_IMM,
                1,
                BC.STORE_MEM,
                slots[4],
                BC.JMP,
                lbl_lshift_loop,
            ]
        )

        # Done shifting
        lbl_done = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_rshift_end] = lbl_done
        bytecode[patch_lshift_end] = lbl_done

        # Apply sign
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[3],
                BC.STORE_MEM,
                slots[5],
                BC.LOAD_MEM,
                slots[1],
                BC.EQ_IMM,
                0,
                BC.JMP_T,
                -1,
            ]
        )
        patch_no_neg = len(bytecode) - 1
        bytecode.extend(
            [
                BC.LOAD_IMM,
                0,
                BC.SUB_MEM,
                slots[5],
                BC.STORE_MEM,
                slots[5],
            ]
        )
        lbl_finish = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_no_neg] = lbl_finish
        bytecode.extend([BC.JMP, -1])
        patch_to_finish = len(bytecode) - 1

        # Zero result
        lbl_zero = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_zero] = lbl_zero
        bytecode.extend(
            [
                BC.LOAD_IMM,
                0,
                BC.STORE_MEM,
                slots[5],
            ]
        )

        lbl_final = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_to_finish] = lbl_final

        compiler.Compiler.emit_write_args_inplace(unit, [[BC.LOAD_MEM, slots[5]]])
        compiler.Compiler.emit_load_k(unit, k)
        compiler.Compiler.emit_apply_k(unit)

    return BuiltinSymbol(
        source="to-integer",
        path=TreePathEntry.for_builtin("to-integer<float>").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.FLOAT,
                FunctionLanguageType([PrimitiveLanguageType.INTEGER], typevar_emitter()),
            ],
            PrimitiveLanguageType.VOID,
        ),
        emit_inplace=None,
        emit_lambda=LambdaEmitter(
            slots=["INPUT", "SIGN", "EXP", "MANT", "SHIFT", "RESULT"],
            bytecode_emitter=emit_bytecode,
        ),
    )


def builtin_to_float_from_integer():
    """Convert integer to IEEE 754 float bit pattern."""

    def emit_bytecode(unit, slots, k, *args):
        bytecode = unit.bytecode

        # slots: INPUT(0), SIGN(1), MANT(2), EXP(3), RESULT(4)
        bytecode.extend(
            [
                BC.LOAD_MEM,
                args[0],
                BC.STORE_MEM,
                slots[0],
                BC.LOAD_IMM,
                0,
                BC.STORE_MEM,
                slots[1],  # SIGN = 0
            ]
        )

        # Check for zero
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[0],
                BC.EQ_IMM,
                0,
                BC.JMP_T,
                -1,
            ]
        )
        patch_zero = len(bytecode) - 1

        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[0],
                BC.GE_IMM,
                0,
                BC.JMP_T,
                -1,
            ]
        )
        patch_pos = len(bytecode) - 1
        bytecode.extend(
            [
                BC.LOAD_IMM,
                1,
                BC.STORE_MEM,
                slots[1],
                BC.LOAD_IMM,
                0,
                BC.SUB_MEM,
                slots[0],
                BC.STORE_MEM,
                slots[0],
            ]
        )

        lbl_pos = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_pos] = lbl_pos

        # MANT = INPUT, EXP = 150 (bias 127 + 23 mantissa bits)
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[0],
                BC.STORE_MEM,
                slots[2],
                BC.LOAD_IMM,
                150,
                BC.STORE_MEM,
                slots[3],
            ]
        )

        # Normalize: shift left while MANT < 0x800000
        lbl_norm_up = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[2],
                BC.GE_IMM,
                0x800000,
                BC.JMP_T,
                -1,
            ]
        )
        patch_norm_up_end = len(bytecode) - 1
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[2],
                BC.MUL_IMM,
                2,
                BC.STORE_MEM,
                slots[2],
                BC.LOAD_MEM,
                slots[3],
                BC.SUB_IMM,
                1,
                BC.STORE_MEM,
                slots[3],
                BC.JMP,
                lbl_norm_up,
            ]
        )

        lbl_after_norm_up = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_norm_up_end] = lbl_after_norm_up

        # Normalize: shift right while MANT >= 0x1000000
        lbl_norm_down = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[2],
                BC.LT_IMM,
                0x1000000,
                BC.JMP_T,
                -1,
            ]
        )
        patch_norm_down_end = len(bytecode) - 1
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[2],
                BC.DIV_IMM,
                2,
                BC.STORE_MEM,
                slots[2],
                BC.LOAD_MEM,
                slots[3],
                BC.ADD_IMM,
                1,
                BC.STORE_MEM,
                slots[3],
                BC.JMP,
                lbl_norm_down,
            ]
        )

        lbl_after_norm_down = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_norm_down_end] = lbl_after_norm_down

        # Compose: RESULT = (SIGN << 31) | (EXP << 23) | (MANT & 0x7FFFFF)
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[1],
                BC.ASL_IMM,
                31,  # SIGN << 31
                BC.STORE_MEM,
                slots[4],
                BC.LOAD_MEM,
                slots[3],
                BC.MUL_IMM,
                0x800000,  # EXP << 23
                BC.OR_MEM,
                slots[4],
                BC.STORE_MEM,
                slots[4],
                BC.LOAD_MEM,
                slots[2],
                BC.AND_IMM,
                0x7FFFFF,
                BC.OR_MEM,
                slots[4],
                BC.STORE_MEM,
                slots[4],
                BC.JMP,
                -1,
            ]
        )
        patch_to_finish = len(bytecode) - 1

        # Zero
        lbl_zero = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_zero] = lbl_zero
        bytecode.extend(
            [
                BC.LOAD_IMM,
                0,
                BC.STORE_MEM,
                slots[4],
            ]
        )

        lbl_finish = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_to_finish] = lbl_finish

        compiler.Compiler.emit_write_args_inplace(unit, [[BC.LOAD_MEM, slots[4]]])
        compiler.Compiler.emit_load_k(unit, k)
        compiler.Compiler.emit_apply_k(unit)

    return BuiltinSymbol(
        source="to-float",
        path=TreePathEntry.for_builtin("to-float<integer>").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.INTEGER,
                FunctionLanguageType([PrimitiveLanguageType.FLOAT], typevar_emitter()),
            ],
            PrimitiveLanguageType.VOID,
        ),
        emit_inplace=None,
        emit_lambda=LambdaEmitter(
            slots=["INPUT", "SIGN", "MANT", "EXP", "RESULT"],
            bytecode_emitter=emit_bytecode,
        ),
    )


def builtin_floats() -> list[BuiltinSymbol]:
    """Return all non-generic float builtin symbols.

    Note: to-string<float>, to-integer<float>, to-float<integer> are registered
    via generic_builtin_symbols_builders() instead.
    """
    return [
        builtin_to_float_unchecked_string(),
    ]
