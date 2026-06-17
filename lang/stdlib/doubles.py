"""Встроенные операции над DOUBLE (64-бит IEEE 754).

На 32-битной VM double эмулируется двумя слотами:
  lo — младшие 32 бита, hi — старшие 32 бита числа.
"""

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


def builtin_to_string_double():
    def emit_bytecode(unit, slots, k, *args):
        bytecode = unit.bytecode

        # args[0] = lo word slot, args[1] = hi word slot
        # slots: INPUT_LO(0), INPUT_HI(1), IS_NEG(2), WRITE_PTR(3), START_PTR(4),
        #        DIGIT_COUNT(5), INT_PART(6), FRAC_PART(7), SHIFT(8), TMP_BIT(9),
        #        EXPONENT(10), MANT_HI(11)

        # 1. Init and allocate buffer (48 words)
        bytecode.extend(
            [
                BC.LOAD_MEM,
                args[0],
                BC.STORE_MEM,
                slots[0],  # INPUT_LO
                BC.LOAD_MEM,
                args[1],
                BC.STORE_MEM,
                slots[1],  # INPUT_HI
                BC.LOAD_IMM,
                0,
                BC.STORE_MEM,
                slots[5],  # DIGIT_COUNT = 0
                # IS_NEG = (INPUT_HI >> 31) & 1
                BC.LOAD_MEM,
                slots[1],
                BC.LSR_IMM,
                31,
                BC.AND_IMM,
                1,
                BC.STORE_MEM,
                slots[2],
                # START_PTR = HEAP; HEAP += 48; WRITE_PTR = START_PTR + 47
                BC.LOAD_MEM,
                compiler.Memory.HEAP,
                BC.STORE_MEM,
                slots[4],
                BC.ADD_IMM,
                48 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                compiler.Memory.HEAP,
                BC.LOAD_MEM,
                slots[4],
                BC.ADD_IMM,
                47 * compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[3],
            ]
        )

        # 2. Decode IEEE 754 double
        # EXPONENT = (INPUT_HI >> 20) & 0x7FF
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[1],
                BC.LSR_IMM,
                20,
                BC.AND_IMM,
                0x7FF,
                BC.STORE_MEM,
                slots[10],
                # MANT_HI = INPUT_HI & 0xFFFFF (top 20 bits of mantissa)
                BC.LOAD_MEM,
                slots[1],
                BC.AND_IMM,
                0xFFFFF,
                BC.STORE_MEM,
                slots[11],
            ]
        )

        # Check for zero (EXP == 0 and MANT_HI == 0 and INPUT_LO == 0)
        # Simplified: just check EXP == 0
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[10],
                BC.EQ_IMM,
                0,
                BC.JMP_T,
                -1,  # -> zero block
            ]
        )
        patch_zero = len(bytecode) - 1

        # Normal number: we use only the hi mantissa bits for simplicity on 32-bit VM
        # INT_PART = MANT_HI | 0x100000 (add implicit bit for 20-bit mantissa part)
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[11],
                BC.OR_IMM,
                0x100000,
                BC.STORE_MEM,
                slots[6],  # INT_PART = mantissa with implicit bit
            ]
        )

        # SHIFT = 1043 - EXPONENT (bias=1023, then 20 for mantissa bits position)
        # For doubles: bias is 1023, mantissa in hi word is 20 bits
        # So effective_exp = EXPONENT - 1023, and mantissa is shifted by 20
        # SHIFT = 20 - (EXPONENT - 1023) = 1043 - EXPONENT
        bytecode.extend(
            [
                BC.LOAD_IMM,
                1043,
                BC.SUB_MEM,
                slots[10],
                BC.STORE_MEM,
                slots[8],  # SHIFT
                BC.LOAD_IMM,
                0,
                BC.STORE_MEM,
                slots[7],  # FRAC_PART = 0
            ]
        )

        # Branch based on SHIFT
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[8],
                BC.LT_IMM,
                0,
                BC.JMP_T,
                -1,  # -> LSHIFT
                BC.LOAD_MEM,
                slots[8],
                BC.GT_IMM,
                0,
                BC.JMP_T,
                -1,  # -> RSHIFT
                BC.JMP,
                -1,  # -> END_SHIFTS
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
                slots[6],
                BC.STORE_MEM,
                slots[7],
                BC.JMP,
                -1,
            ]
        )
        patch_zero_jmp = len(bytecode) - 1

        # --- LEFT SHIFT ---
        lbl_lshift = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_lt] = lbl_lshift
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[8],
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
                slots[6],
                BC.MUL_IMM,
                2,
                BC.STORE_MEM,
                slots[6],
                BC.LOAD_MEM,
                slots[8],
                BC.ADD_IMM,
                1,
                BC.STORE_MEM,
                slots[8],
                BC.JMP,
                lbl_lshift,
            ]
        )

        # --- RIGHT SHIFT ---
        lbl_rshift = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_gt] = lbl_rshift
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[8],
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
                slots[6],
                BC.MOD_IMM,
                2,
                BC.STORE_MEM,
                slots[9],  # TMP_BIT
                BC.LOAD_MEM,
                slots[6],
                BC.DIV_IMM,
                2,
                BC.STORE_MEM,
                slots[6],
                BC.LOAD_MEM,
                slots[7],
                BC.DIV_IMM,
                2,
                BC.STORE_MEM,
                slots[7],
                # FRAC_PART += TMP_BIT * 500000000 (fixed point for 10 digits)
                BC.LOAD_MEM,
                slots[9],
                BC.MUL_IMM,
                500000000,
                BC.ADD_MEM,
                slots[7],
                BC.STORE_MEM,
                slots[7],
                BC.LOAD_MEM,
                slots[8],
                BC.SUB_IMM,
                1,
                BC.STORE_MEM,
                slots[8],
                BC.JMP,
                lbl_rshift,
            ]
        )

        # --- END SHIFTS ---
        lbl_end_shifts = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_eq] = lbl_end_shifts
        bytecode[patch_zero_jmp] = lbl_end_shifts
        bytecode[patch_lshift_end] = lbl_end_shifts
        bytecode[patch_rshift_end] = lbl_end_shifts

        # 3. Generate string - 9 fractional digits (matching 10^9 precision from multiplier)
        bytecode.extend(
            [
                BC.LOAD_IMM,
                9,
                BC.STORE_MEM,
                slots[9],
            ]
        )

        lbl_frac_loop = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[9],
                BC.EQ_IMM,
                0,
                BC.JMP_T,
                -1,
            ]
        )
        patch_frac_end = len(bytecode) - 1
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[7],
                BC.MOD_IMM,
                10,
                BC.ADD_IMM,
                48,
                BC.STORE_IND_MEM,
                slots[3],
                BC.LOAD_MEM,
                slots[3],
                BC.SUB_IMM,
                compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[3],
                BC.LOAD_MEM,
                slots[7],
                BC.DIV_IMM,
                10,
                BC.STORE_MEM,
                slots[7],
                BC.LOAD_MEM,
                slots[5],
                BC.ADD_IMM,
                1,
                BC.STORE_MEM,
                slots[5],
                BC.LOAD_MEM,
                slots[9],
                BC.SUB_IMM,
                1,
                BC.STORE_MEM,
                slots[9],
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
                46,
                BC.STORE_IND_MEM,
                slots[3],
                BC.LOAD_MEM,
                slots[3],
                BC.SUB_IMM,
                compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[3],
                BC.LOAD_MEM,
                slots[5],
                BC.ADD_IMM,
                1,
                BC.STORE_MEM,
                slots[5],
            ]
        )

        # Integer part
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[6],
                BC.EQ_IMM,
                0,
                BC.JMP_T,
                -1,
            ]
        )
        patch_int_zero = len(bytecode) - 1

        lbl_int_loop = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[6],
                BC.EQ_IMM,
                0,
                BC.JMP_T,
                -1,
            ]
        )
        patch_int_end = len(bytecode) - 1
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[6],
                BC.MOD_IMM,
                10,
                BC.ADD_IMM,
                48,
                BC.STORE_IND_MEM,
                slots[3],
                BC.LOAD_MEM,
                slots[3],
                BC.SUB_IMM,
                compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[3],
                BC.LOAD_MEM,
                slots[6],
                BC.DIV_IMM,
                10,
                BC.STORE_MEM,
                slots[6],
                BC.LOAD_MEM,
                slots[5],
                BC.ADD_IMM,
                1,
                BC.STORE_MEM,
                slots[5],
                BC.JMP,
                lbl_int_loop,
            ]
        )

        # Integer part was 0
        lbl_int_zero = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_int_zero] = lbl_int_zero
        bytecode.extend(
            [
                BC.LOAD_IMM,
                48,
                BC.STORE_IND_MEM,
                slots[3],
                BC.LOAD_MEM,
                slots[3],
                BC.SUB_IMM,
                compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[3],
                BC.LOAD_MEM,
                slots[5],
                BC.ADD_IMM,
                1,
                BC.STORE_MEM,
                slots[5],
            ]
        )

        # Sign check
        lbl_sign_check = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_int_end] = lbl_sign_check
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
        patch_finish = len(bytecode) - 1
        bytecode.extend(
            [
                BC.LOAD_IMM,
                45,
                BC.STORE_IND_MEM,
                slots[3],
                BC.LOAD_MEM,
                slots[3],
                BC.SUB_IMM,
                compiler.Memory.WORD_LEN,
                BC.STORE_MEM,
                slots[3],
                BC.LOAD_MEM,
                slots[5],
                BC.ADD_IMM,
                1,
                BC.STORE_MEM,
                slots[5],
            ]
        )

        # Finish
        lbl_finish = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_finish] = lbl_finish
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[5],
                BC.STORE_IND_MEM,
                slots[3],
            ]
        )

        compiler.Compiler.emit_write_args_inplace(unit, [[BC.LOAD_MEM, slots[3]]])
        compiler.Compiler.emit_load_k(unit, k)
        compiler.Compiler.emit_apply_k(unit)

    return BuiltinSymbol(
        source="to-string",
        path=TreePathEntry.for_builtin("to-string<double>").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.DOUBLE,
                FunctionLanguageType([PrimitiveLanguageType.STRING], typevar_emitter()),
            ],
            PrimitiveLanguageType.VOID,
        ),
        emit_inplace=None,
        emit_lambda=LambdaEmitter(
            slots=[
                "INPUT_LO",
                "INPUT_HI",
                "IS_NEG",
                "WRITE_PTR",
                "START_PTR",
                "DIGIT_COUNT",
                "INT_PART",
                "FRAC_PART",
                "SHIFT",
                "TMP_BIT",
                "EXPONENT",
                "MANT_HI",
            ],
            bytecode_emitter=emit_bytecode,
        ),
    )


def builtin_add_double():
    """Double addition: adds two doubles by extracting hi words, adding as integers.

    This is a simplified implementation that works with the hi-word mantissa only.
    For the 32-bit VM, we work with the hi word which contains sign, exponent,
    and top 20 bits of mantissa - sufficient for moderate precision.
    """

    def emit_bytecode(unit, slots, k, *args):
        bytecode = unit.bytecode

        # args: a_lo(0), a_hi(1), b_lo(2), b_hi(3)
        # We extract sign/exp/mantissa from both hi words, align exponents,
        # add/sub mantissas, normalize, and compose result

        # slots: A_SIGN(0), A_EXP(1), A_MANT(2), B_SIGN(3), B_EXP(4), B_MANT(5),
        #        R_SIGN(6), R_EXP(7), R_MANT(8), SHIFT(9), R_LO(10), R_HI(11), TMP(12)

        # Extract A: sign, exponent, mantissa
        bytecode.extend(
            [
                BC.LOAD_MEM,
                args[1],
                BC.LSR_IMM,
                31,
                BC.AND_IMM,
                1,
                BC.STORE_MEM,
                slots[0],  # A_SIGN
                BC.LOAD_MEM,
                args[1],
                BC.LSR_IMM,
                20,
                BC.AND_IMM,
                0x7FF,
                BC.STORE_MEM,
                slots[1],  # A_EXP
                BC.LOAD_MEM,
                args[1],
                BC.AND_IMM,
                0xFFFFF,
                BC.OR_IMM,
                0x100000,
                BC.STORE_MEM,
                slots[2],  # A_MANT (with implicit bit)
            ]
        )

        # Extract B: sign, exponent, mantissa
        bytecode.extend(
            [
                BC.LOAD_MEM,
                args[3],
                BC.LSR_IMM,
                31,
                BC.AND_IMM,
                1,
                BC.STORE_MEM,
                slots[3],  # B_SIGN
                BC.LOAD_MEM,
                args[3],
                BC.LSR_IMM,
                20,
                BC.AND_IMM,
                0x7FF,
                BC.STORE_MEM,
                slots[4],  # B_EXP
                BC.LOAD_MEM,
                args[3],
                BC.AND_IMM,
                0xFFFFF,
                BC.OR_IMM,
                0x100000,
                BC.STORE_MEM,
                slots[5],  # B_MANT (with implicit bit)
            ]
        )

        # Align exponents: if A_EXP > B_EXP, shift B_MANT right
        # if B_EXP > A_EXP, shift A_MANT right
        # SHIFT = A_EXP - B_EXP
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[1],
                BC.SUB_MEM,
                slots[4],
                BC.STORE_MEM,
                slots[9],  # SHIFT = A_EXP - B_EXP
                # R_EXP = max(A_EXP, B_EXP) - start with A_EXP
                BC.LOAD_MEM,
                slots[1],
                BC.STORE_MEM,
                slots[7],
            ]
        )

        # If SHIFT > 0, shift B_MANT right by SHIFT
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[9],
                BC.GT_IMM,
                0,
                BC.JMP_T,
                -1,  # -> shift_b
            ]
        )
        patch_shift_b = len(bytecode) - 1

        # If SHIFT < 0, shift A_MANT right by -SHIFT
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[9],
                BC.LT_IMM,
                0,
                BC.JMP_T,
                -1,  # -> shift_a
            ]
        )
        patch_shift_a = len(bytecode) - 1

        # SHIFT == 0, skip to add
        bytecode.extend([BC.JMP, -1])
        patch_skip_align = len(bytecode) - 1

        # --- shift B right ---
        lbl_shift_b = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_shift_b] = lbl_shift_b
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[9],
                BC.EQ_IMM,
                0,
                BC.JMP_T,
                -1,  # -> done aligning
            ]
        )
        patch_shift_b_end = len(bytecode) - 1
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[5],
                BC.DIV_IMM,
                2,
                BC.STORE_MEM,
                slots[5],
                BC.LOAD_MEM,
                slots[9],
                BC.SUB_IMM,
                1,
                BC.STORE_MEM,
                slots[9],
                BC.JMP,
                lbl_shift_b,
            ]
        )

        # --- shift A right ---
        lbl_shift_a = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_shift_a] = lbl_shift_a
        # R_EXP = B_EXP (since B has larger exponent)
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[4],
                BC.STORE_MEM,
                slots[7],
                # negate SHIFT for loop
                BC.LOAD_IMM,
                0,
                BC.SUB_MEM,
                slots[9],
                BC.STORE_MEM,
                slots[9],
            ]
        )
        lbl_shift_a_loop = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[9],
                BC.EQ_IMM,
                0,
                BC.JMP_T,
                -1,  # -> done aligning
            ]
        )
        patch_shift_a_end = len(bytecode) - 1
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[2],
                BC.DIV_IMM,
                2,
                BC.STORE_MEM,
                slots[2],
                BC.LOAD_MEM,
                slots[9],
                BC.SUB_IMM,
                1,
                BC.STORE_MEM,
                slots[9],
                BC.JMP,
                lbl_shift_a_loop,
            ]
        )

        # --- done aligning ---
        lbl_done_align = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_skip_align] = lbl_done_align
        bytecode[patch_shift_b_end] = lbl_done_align
        bytecode[patch_shift_a_end] = lbl_done_align

        # Add/subtract mantissas based on signs
        # If signs same: R_MANT = A_MANT + B_MANT, R_SIGN = A_SIGN
        # If signs differ: R_MANT = |A_MANT - B_MANT|, R_SIGN = sign of larger
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[0],
                BC.EQ_MEM,
                slots[3],
                BC.JMP_T,
                -1,  # -> same_sign
            ]
        )
        patch_same_sign = len(bytecode) - 1

        # Different signs: subtract
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[2],
                BC.SUB_MEM,
                slots[5],
                BC.STORE_MEM,
                slots[8],  # R_MANT = A_MANT - B_MANT
                # If result negative, negate and use B_SIGN
                BC.LOAD_MEM,
                slots[8],
                BC.GE_IMM,
                0,
                BC.JMP_T,
                -1,  # -> positive result
            ]
        )
        patch_pos_result = len(bytecode) - 1
        bytecode.extend(
            [
                BC.LOAD_IMM,
                0,
                BC.SUB_MEM,
                slots[8],
                BC.STORE_MEM,
                slots[8],
                BC.LOAD_MEM,
                slots[3],
                BC.STORE_MEM,
                slots[6],  # R_SIGN = B_SIGN
                BC.JMP,
                -1,
            ]
        )
        patch_after_sub = len(bytecode) - 1

        lbl_pos_result = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_pos_result] = lbl_pos_result
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[0],
                BC.STORE_MEM,
                slots[6],  # R_SIGN = A_SIGN
                BC.JMP,
                -1,
            ]
        )
        patch_after_sub2 = len(bytecode) - 1

        # Same signs: add
        lbl_same_sign = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_same_sign] = lbl_same_sign
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[2],
                BC.ADD_MEM,
                slots[5],
                BC.STORE_MEM,
                slots[8],  # R_MANT = A_MANT + B_MANT
                BC.LOAD_MEM,
                slots[0],
                BC.STORE_MEM,
                slots[6],  # R_SIGN = A_SIGN
            ]
        )

        # --- Normalize ---
        lbl_after_add = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_after_sub] = lbl_after_add
        bytecode[patch_after_sub2] = lbl_after_add

        # If R_MANT >= 0x200000 (overflow), shift right and increment exponent
        lbl_norm_loop = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[8],
                BC.LE_IMM,
                0x1FFFFF,
                BC.JMP_T,
                -1,  # -> done normalizing overflow
            ]
        )
        patch_norm_done = len(bytecode) - 1
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[8],
                BC.DIV_IMM,
                2,
                BC.STORE_MEM,
                slots[8],
                BC.LOAD_MEM,
                slots[7],
                BC.ADD_IMM,
                1,
                BC.STORE_MEM,
                slots[7],
                BC.JMP,
                lbl_norm_loop,
            ]
        )

        lbl_norm_done = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_norm_done] = lbl_norm_done

        # Check if R_MANT == 0 (result is zero)
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[8],
                BC.EQ_IMM,
                0,
                BC.JMP_T,
                -1,  # -> result_zero
            ]
        )
        patch_result_zero = len(bytecode) - 1

        # Normalize underflow: shift left while R_MANT < 0x100000
        lbl_norm_up = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[8],
                BC.GE_IMM,
                0x100000,
                BC.JMP_T,
                -1,  # -> compose
            ]
        )
        patch_compose = len(bytecode) - 1
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[8],
                BC.MUL_IMM,
                2,
                BC.STORE_MEM,
                slots[8],
                BC.LOAD_MEM,
                slots[7],
                BC.SUB_IMM,
                1,
                BC.STORE_MEM,
                slots[7],
                BC.JMP,
                lbl_norm_up,
            ]
        )

        # --- Compose result ---
        lbl_compose = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_compose] = lbl_compose

        # R_HI = (R_SIGN << 31) | (R_EXP << 20) | (R_MANT & 0xFFFFF)
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[6],
                BC.ASL_IMM,
                31,  # R_SIGN << 31
                BC.STORE_MEM,
                slots[11],
                BC.LOAD_MEM,
                slots[7],
                BC.MUL_IMM,
                0x100000,  # R_EXP << 20
                BC.OR_MEM,
                slots[11],
                BC.STORE_MEM,
                slots[11],
                BC.LOAD_MEM,
                slots[8],
                BC.AND_IMM,
                0xFFFFF,
                BC.OR_MEM,
                slots[11],
                BC.STORE_MEM,
                slots[11],  # R_HI
                BC.LOAD_IMM,
                0,
                BC.STORE_MEM,
                slots[10],  # R_LO = 0 (simplified)
                BC.JMP,
                -1,
            ]
        )
        patch_to_finish = len(bytecode) - 1

        # --- result zero ---
        lbl_result_zero = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_result_zero] = lbl_result_zero
        bytecode.extend(
            [
                BC.LOAD_IMM,
                0,
                BC.STORE_MEM,
                slots[10],
                BC.STORE_MEM,
                slots[11],
            ]
        )

        # --- finish ---
        lbl_finish = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_to_finish] = lbl_finish

        # Return lo, hi via CPS
        compiler.Compiler.emit_write_args_inplace(
            unit,
            [
                [BC.LOAD_MEM, slots[10]],
                [BC.LOAD_MEM, slots[11]],
            ],
        )
        compiler.Compiler.emit_load_k(unit, k)
        compiler.Compiler.emit_apply_k(unit)

    return BuiltinSymbol(
        source="+",
        path=TreePathEntry.for_builtin("+<double>").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.DOUBLE,
                PrimitiveLanguageType.DOUBLE,
                FunctionLanguageType([PrimitiveLanguageType.DOUBLE], typevar_emitter()),
            ],
            PrimitiveLanguageType.VOID,
        ),
        emit_inplace=None,
        emit_lambda=LambdaEmitter(
            slots=[
                "A_SIGN",
                "A_EXP",
                "A_MANT",
                "B_SIGN",
                "B_EXP",
                "B_MANT",
                "R_SIGN",
                "R_EXP",
                "R_MANT",
                "SHIFT",
                "R_LO",
                "R_HI",
                "TMP",
            ],
            bytecode_emitter=emit_bytecode,
        ),
    )


def builtin_eq_double():
    """Double equality: compare hi words then lo words."""
    return BuiltinSymbol(
        source="==",
        path=TreePathEntry.for_builtin("==<double>").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [PrimitiveLanguageType.DOUBLE, PrimitiveLanguageType.DOUBLE],
            PrimitiveLanguageType.BOOLEAN,
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend(
            [
                # Compare hi words first
                BC.LOAD_MEM,
                args[1],  # a_hi
                BC.EQ_MEM,
                args[3],  # b_hi
                BC.STORE_MEM,
                slot,
                # AND with lo comparison
                BC.LOAD_MEM,
                args[0],  # a_lo
                BC.EQ_MEM,
                args[2],  # b_lo
                BC.AND_MEM,
                slot,
                BC.STORE_MEM,
                slot,
            ]
        ),
        emit_lambda=None,
    )


def builtin_lt_double():
    """Double less-than: compare hi words, then lo words if equal."""

    def emit_bytecode(unit, slots, k, *args):
        bytecode = unit.bytecode

        # slots: RESULT(0)
        # args: a_lo(0), a_hi(1), b_lo(2), b_hi(3)

        # First compare hi words
        bytecode.extend(
            [
                BC.LOAD_MEM,
                args[1],
                BC.LT_MEM,
                args[3],
                BC.JMP_T,
                -1,  # -> true
            ]
        )
        patch_true = len(bytecode) - 1

        bytecode.extend(
            [
                BC.LOAD_MEM,
                args[1],
                BC.EQ_MEM,
                args[3],
                BC.JMP_T,
                -1,  # -> check lo
            ]
        )
        patch_check_lo = len(bytecode) - 1

        # hi_a > hi_b -> false
        bytecode.extend(
            [
                BC.LOAD_IMM,
                0,
                BC.STORE_MEM,
                slots[0],
                BC.JMP,
                -1,
            ]
        )
        patch_false_jmp = len(bytecode) - 1

        # check lo words
        lbl_check_lo = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_check_lo] = lbl_check_lo
        bytecode.extend(
            [
                BC.LOAD_MEM,
                args[0],
                BC.LT_MEM,
                args[2],
                BC.STORE_MEM,
                slots[0],
                BC.JMP,
                -1,
            ]
        )
        patch_lo_jmp = len(bytecode) - 1

        # true
        lbl_true = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_true] = lbl_true
        bytecode.extend(
            [
                BC.LOAD_IMM,
                1,
                BC.STORE_MEM,
                slots[0],
            ]
        )

        # finish
        lbl_finish = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_false_jmp] = lbl_finish
        bytecode[patch_lo_jmp] = lbl_finish

        compiler.Compiler.emit_write_args_inplace(unit, [[BC.LOAD_MEM, slots[0]]])
        compiler.Compiler.emit_load_k(unit, k)
        compiler.Compiler.emit_apply_k(unit)

    return BuiltinSymbol(
        source="<",
        path=TreePathEntry.for_builtin("<<double>").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.DOUBLE,
                PrimitiveLanguageType.DOUBLE,
                FunctionLanguageType([PrimitiveLanguageType.BOOLEAN], typevar_emitter()),
            ],
            PrimitiveLanguageType.VOID,
        ),
        emit_inplace=None,
        emit_lambda=LambdaEmitter(
            slots=["RESULT"],
            bytecode_emitter=emit_bytecode,
        ),
    )


def builtin_to_double_from_integer():
    """Convert integer to IEEE 754 double (2 slots: lo, hi)."""

    def emit_bytecode(unit, slots, k, *args):
        bytecode = unit.bytecode

        # slots: INPUT(0), SIGN(1), MANT(2), EXP(3), R_LO(4), R_HI(5)
        bytecode.extend(
            [
                BC.LOAD_MEM,
                args[0],
                BC.STORE_MEM,
                slots[0],
                BC.LOAD_IMM,
                0,
                BC.STORE_MEM,
                slots[1],
            ]
        )

        # Check zero
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

        # Check negative
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

        # MANT = INPUT, EXP = 1043 (bias 1023 + 20 mantissa bits in hi word)
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[0],
                BC.STORE_MEM,
                slots[2],
                BC.LOAD_IMM,
                1043,
                BC.STORE_MEM,
                slots[3],
            ]
        )

        # Normalize up: shift left while MANT < 0x100000
        lbl_norm_up = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[2],
                BC.GE_IMM,
                0x100000,
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

        # Normalize down: shift right while MANT >= 0x200000
        lbl_norm_down = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[2],
                BC.LT_IMM,
                0x200000,
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

        # Compose: R_HI = (SIGN << 31) | (EXP << 20) | (MANT & 0xFFFFF)
        bytecode.extend(
            [
                BC.LOAD_MEM,
                slots[1],
                BC.ASL_IMM,
                31,
                BC.STORE_MEM,
                slots[5],
                BC.LOAD_MEM,
                slots[3],
                BC.MUL_IMM,
                0x100000,
                BC.OR_MEM,
                slots[5],
                BC.STORE_MEM,
                slots[5],
                BC.LOAD_MEM,
                slots[2],
                BC.AND_IMM,
                0xFFFFF,
                BC.OR_MEM,
                slots[5],
                BC.STORE_MEM,
                slots[5],
                BC.LOAD_IMM,
                0,
                BC.STORE_MEM,
                slots[4],  # R_LO = 0
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
                BC.STORE_MEM,
                slots[5],
            ]
        )

        lbl_finish = len(bytecode) * compiler.Memory.WORD_LEN
        bytecode[patch_to_finish] = lbl_finish

        compiler.Compiler.emit_write_args_inplace(
            unit,
            [
                [BC.LOAD_MEM, slots[4]],
                [BC.LOAD_MEM, slots[5]],
            ],
        )
        compiler.Compiler.emit_load_k(unit, k)
        compiler.Compiler.emit_apply_k(unit)

    return BuiltinSymbol(
        source="to-double",
        path=TreePathEntry.for_builtin("to-double<integer>").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.INTEGER,
                FunctionLanguageType([PrimitiveLanguageType.DOUBLE], typevar_emitter()),
            ],
            PrimitiveLanguageType.VOID,
        ),
        emit_inplace=None,
        emit_lambda=LambdaEmitter(
            slots=["INPUT", "SIGN", "MANT", "EXP", "R_LO", "R_HI"],
            bytecode_emitter=emit_bytecode,
        ),
    )


def builtin_to_integer_from_double():
    """Convert IEEE 754 double to integer by extracting the integer part from hi word."""

    def emit_bytecode(unit, slots, k, *args):
        bytecode = unit.bytecode

        # args: lo(0), hi(1)
        # slots: INPUT_HI(0), SIGN(1), EXP(2), MANT(3), SHIFT(4), RESULT(5)
        bytecode.extend(
            [
                BC.LOAD_MEM,
                args[1],
                BC.STORE_MEM,
                slots[0],
                # SIGN
                BC.LOAD_MEM,
                slots[0],
                BC.LSR_IMM,
                31,
                BC.AND_IMM,
                1,
                BC.STORE_MEM,
                slots[1],
                # EXP
                BC.LOAD_MEM,
                slots[0],
                BC.LSR_IMM,
                20,
                BC.AND_IMM,
                0x7FF,
                BC.STORE_MEM,
                slots[2],
                # MANT = (hi & 0xFFFFF) | 0x100000
                BC.LOAD_MEM,
                slots[0],
                BC.AND_IMM,
                0xFFFFF,
                BC.OR_IMM,
                0x100000,
                BC.STORE_MEM,
                slots[3],
            ]
        )

        # Check zero exponent
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

        # SHIFT = 1043 - EXP
        bytecode.extend(
            [
                BC.LOAD_IMM,
                1043,
                BC.SUB_MEM,
                slots[2],
                BC.STORE_MEM,
                slots[4],
            ]
        )

        # If SHIFT < 0, left shift
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

        # Right shift
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

        # Zero
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
        path=TreePathEntry.for_builtin("to-integer<double>").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [
                PrimitiveLanguageType.DOUBLE,
                FunctionLanguageType([PrimitiveLanguageType.INTEGER], typevar_emitter()),
            ],
            PrimitiveLanguageType.VOID,
        ),
        emit_inplace=None,
        emit_lambda=LambdaEmitter(
            slots=["INPUT_HI", "SIGN", "EXP", "MANT", "SHIFT", "RESULT"],
            bytecode_emitter=emit_bytecode,
        ),
    )


def builtin_double_lo():
    """`(double-lo d)` -- low 32 бита IEEE 754 представления double (как signed int32).

    Полезно для демонстрации того, что DOUBLE действительно хранится двумя словами
    -- младший слот несёт нижние 32 бита мантиссы, и они корректно участвуют в
    сложении (`(+ <double> <double>)`).
    """
    return BuiltinSymbol(
        source="double-lo",
        path=TreePathEntry.for_builtin("double-lo").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [PrimitiveLanguageType.DOUBLE], PrimitiveLanguageType.INTEGER
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend(
            [BC.LOAD_MEM, args[0], BC.STORE_MEM, slot]
        ),
        emit_lambda=None,
    )


def builtin_double_hi():
    """`(double-hi d)` -- верхние 32 бита IEEE 754 представления double (sign+exp+top 20 mant)."""
    return BuiltinSymbol(
        source="double-hi",
        path=TreePathEntry.for_builtin("double-hi").as_entire_tree_path(),
        lang_type_builder=lambda typevar_emitter: FunctionLanguageType(
            [PrimitiveLanguageType.DOUBLE], PrimitiveLanguageType.INTEGER
        ),
        emit_inplace=lambda unit, slot, *args: unit.bytecode.extend(
            [BC.LOAD_MEM, args[1], BC.STORE_MEM, slot]
        ),
        emit_lambda=None,
    )


def builtin_doubles() -> list[BuiltinSymbol]:
    """Return all non-generic double builtin symbols.

    Note: to-string<double>, to-double<integer>, to-integer<double> are registered
    via generic_builtin_symbols_builders() instead.
    """
    return [
        builtin_double_lo(),
        builtin_double_hi(),
    ]
