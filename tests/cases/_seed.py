from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent


CASES: dict[str, list[tuple[str, str, dict]]] = {
    "arithmetic": [
        ("simple_addition", "(+ 2 3)", {"acc": 5, "output": ""}),
        ("addition_three_args", "(+ (+ 10 20) 30)", {"acc": 60, "output": ""}),
        ("subtraction", "(- 10 3)", {"acc": 7, "output": ""}),
        ("multiplication", "(* 4 5)", {"acc": 20, "output": ""}),
        ("division", "(/ 20 4)", {"acc": 5, "output": ""}),
        ("modulo", "(mod 17 5)", {"acc": 2, "output": ""}),
        ("nested", "(+ (* 2 3) (- 10 4))", {"acc": 12, "output": ""}),
    ],
    "comparison": [
        ("eq_true", "(== 5 5)", {"acc": 1, "output": ""}),
        ("eq_false", "(== 5 3)", {"acc": 0, "output": ""}),
        ("lt", "(< 3 5)", {"acc": 1, "output": ""}),
        ("le", "(<= 5 5)", {"acc": 1, "output": ""}),
        ("gt", "(> 10 3)", {"acc": 1, "output": ""}),
    ],
    "logic": [
        ("and_true", "(and (== 1 1) (== 2 2))", {"acc": 1, "output": ""}),
        ("and_false", "(and (== 1 1) (== 2 3))", {"acc": 0, "output": ""}),
        ("or_true", "(or (== 1 2) (== 2 2))", {"acc": 1, "output": ""}),
        ("or_false", "(or (== 1 2) (== 3 4))", {"acc": 0, "output": ""}),
    ],
    "conditional": [
        ("if_true", "(if (== 1 1) 42 99)", {"acc": 42, "output": ""}),
        ("if_false", "(if (== 1 2) 42 99)", {"acc": 99, "output": ""}),
        ("nested_if", "(if (> 10 5) (if (< 3 7) 1 2) 3)", {"acc": 1, "output": ""}),
    ],
    "functions": [
        (
            "square",
            "(defun square (x) (* x x))\n(square 5)\n",
            {"acc": 25, "output": ""},
        ),
        (
            "multi_args",
            "(defun add-three (a b c) (+ (+ a b) c))\n(add-three 10 20 30)\n",
            {"acc": 60, "output": ""},
        ),
        (
            "recursive_factorial",
            "(defun factorial (n)\n  (if (<= n 1) 1 (* n (factorial (- n 1)))))\n(factorial 5)\n",
            {"acc": 120, "output": ""},
        ),
        (
            "fibonacci",
            "(defun fib (n)\n  (if (<= n 1) n (+ (fib (- n 1)) (fib (- n 2)))))\n(fib 10)\n",
            {"acc": 55, "output": ""},
        ),
    ],
    "strings": [
        ("hello", '(print "Hello, World!")', {"acc": 0, "output": "Hello, World!"}),
        ("concat", '(print (concat "Hello" " World"))', {"acc": 0, "output": "Hello World"}),
        ("int_to_string", "(print (to-string 123))", {"acc": 0, "output": "123"}),
        ("neg_int_to_string", "(print (to-string -456))", {"acc": 0, "output": "-456"}),
        ("float_to_string", "(print (to-string 3.14))", {"acc": 0, "output": "3.14000"}),
    ],
    "lambda": [
        ("simple_lambda", "((lambda (x) (* x x)) 7)", {"acc": 49, "output": ""}),
        (
            "closure",
            "((lambda (x) ((lambda (y) (+ x y)) 10)) 5)",
            {"acc": 15, "output": ""},
        ),
    ],
    "complex": [
        (
            "sum_of_multiples",
            "(defun sum-multiples (n acc)\n"
            "  (if (== n 0)\n"
            "      acc\n"
            "      (sum-multiples (- n 1)\n"
            "                     (+ acc (if (or (== (mod n 3) 0)\n"
            "                                    (== (mod n 5) 0))\n"
            "                                n\n"
            "                                0)))))\n"
            "(sum-multiples 10 0)\n",
            {"acc": 33, "output": ""},
        ),
        (
            "function_composition",
            "(defun double (x) (* x 2))\n"
            "(defun add-ten (x) (+ x 10))\n"
            "(defun compose (x) (add-ten (double x)))\n"
            "(compose 5)\n",
            {"acc": 20, "output": ""},
        ),
        (
            "conditional_output",
            "(defun check-number (n)\n"
            "  (if (> n 10)\n"
            '      (print "big")\n'
            '      (print "small")))\n'
            "(check-number 15)\n",
            {"acc": 0, "output": "big"},
        ),
        (
            "progn_arithmetic",
            "(progn (+ 1 1) (+ 2 2) (* 3 4))",
            {"acc": 12, "output": ""},
        ),
        (
            "progn_print",
            '(progn (print "Hello") (print "World"))',
            {"acc": 0, "output": "HelloWorld"},
        ),
    ],
    "doubles": [
        (
            "double_precision_64bit",
            "(progn\n"
            '  (print "lo=")\n'
            "  (print (to-string (double-lo (+ 4294967296.0d 4294967296.0d))))\n"
            '  (print " hi=")\n'
            "  (print (to-string (double-hi (+ 4294967296.0d 4294967296.0d)))))\n",
            {"acc": 0, "output": "lo=0 hi=1107296256"},
        ),
        ("to_string_42", "(print (to-string 42.0d))", {"acc": 0, "output": "42.000000000"}),
        ("to_string_zero", "(print (to-string 0.0d))", {"acc": 0, "output": "0.000000000"}),
        ("to_string_one", "(print (to-string 1.0d))", {"acc": 0, "output": "1.000000000"}),
        (
            "to_string_negative",
            "(print (to-string -2.5d))",
            {"acc": 0, "output": "-2.500000000"},
        ),
        (
            "to_string_fractional",
            "(print (to-string 3.14d))",
            {"acc": 0, "output_startswith": "3.1"},
        ),
        (
            "add_literals",
            "(print (to-string (+ 1.0d 2.0d)))",
            {"acc": 0, "output": "3.000000000"},
        ),
        (
            "add_via_to_double",
            "(print (to-string (+ (to-double 1) (to-double 2))))",
            {"acc": 0, "output": "3.000000000"},
        ),
        (
            "add_mixed",
            "(print (to-string (+ (to-double 5) 3.0d)))",
            {"acc": 0, "output": "8.000000000"},
        ),
    ],
    "type_conversions": [
        (
            "int_to_double",
            "(print (to-string (to-double 42)))",
            {"acc": 0, "output": "42.000000000"},
        ),
        (
            "int_zero_to_double",
            "(print (to-string (to-double 0)))",
            {"acc": 0, "output": "0.000000000"},
        ),
        ("double_to_int", "(print (to-string (to-integer 3.14d)))", {"acc": 0, "output": "3"}),
        ("float_to_int", "(print (to-string (to-integer 7.9)))", {"acc": 0, "output": "7"}),
        ("int_to_float", "(print (to-string (to-float 5)))", {"acc": 0, "output": "5.00000"}),
        (
            "neg_int_to_double",
            "(print (to-string (to-double -10)))",
            {"acc": 0, "output": "-10.000000000"},
        ),
    ],
    "string_addition": [
        ("plus_concat", '(print (+ "hello" " world"))', {"acc": 0, "output": "hello world"}),
    ],
    "first_class": [
        (
            "pass_plus",
            "(defun test (f) (f 1 1))\n(print (to-string (test +)))\n",
            {"acc": 0, "output": "2"},
        ),
        (
            "pass_star",
            "(defun apply-op (f x y) (f x y))\n(print (to-string (apply-op * 3 4)))\n",
            {"acc": 0, "output": "12"},
        ),
    ],
    "setq": [
        (
            "simple",
            "(defun test (x) (progn (setq x 42) x))\n(test 0)\n",
            {"acc": 42, "output": ""},
        ),
        (
            "with_expression",
            "(defun test (x) (progn (setq x (+ x 10)) x))\n(test 5)\n",
            {"acc": 15, "output": ""},
        ),
    ],
    "while": [
        (
            "sum_1_to_10",
            "(defun sum-to (n acc)\n"
            "  (progn\n"
            "    (while (> n 0)\n"
            "      (progn\n"
            "        (setq acc (+ acc n))\n"
            "        (setq n (- n 1))))\n"
            "    acc))\n"
            "(sum-to 10 0)\n",
            {"acc": 55, "output": ""},
        ),
        (
            "count_down",
            "(defun count-down (n)\n"
            "  (progn (while (> n 0) (setq n (- n 1))) n))\n"
            "(count-down 5)\n",
            {"acc": 0, "output": ""},
        ),
        (
            "factorial",
            "(defun factorial (n result)\n"
            "  (progn\n"
            "    (while (> n 1)\n"
            "      (progn\n"
            "        (setq result (* result n))\n"
            "        (setq n (- n 1))))\n"
            "    result))\n"
            "(factorial 5 1)\n",
            {"acc": 120, "output": ""},
        ),
    ],
    "autoboxing": [
        (
            "mutable_captured_by_lambda",
            "(defun test (x)\n"
            "  ((lambda (f) (progn (setq x 42) (f)))\n"
            "   (lambda () x)))\n"
            "(test 0)\n",
            {"acc": 42, "output": ""},
        ),
    ],
    "euler": [
        (
            "prob1_n1000",
            "(defun triangular (m) (/ (* m (+ m 1)) 2))\n"
            "(defun sum-k (n k) (* k (triangular (/ (- n 1) k))))\n"
            "(- (+ (sum-k 1000 3) (sum-k 1000 5)) (sum-k 1000 15))\n",
            {"acc": 233168, "output": ""},
        ),
    ],
    "io": [
        (
            "cat",
            "(print (input))\n",
            {
                "acc": 0,
                "output": "Hello",
                "input": [5, 72, 101, 108, 108, 111],
            },
        ),
        (
            "hello_user_name",
            "(progn\n"
            '  (print "What is your name?")\n'
            '  (print (concat "Hello, " (concat (input) "!"))))\n',
            {
                "acc": 0,
                "output": "What is your name?Hello, Alice!",
                "input": [5, 65, 108, 105, 99, 101],
            },
        ),
        (
            "sort",
            "((lambda (s)\n   (progn\n     (sort-string! s)\n     (print s)))\n (input))\n",
            {
                "acc": 0,
                "output": "12345",
                "input": [5, 51, 49, 53, 50, 52],
            },
        ),
    ],
}


def main() -> None:
    written = 0
    for category, cases in CASES.items():
        cat_dir = HERE / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        for name, source, expected in cases:
            lisp_path = cat_dir / f"{name}.lisp"
            json_path = cat_dir / f"{name}.json"
            lisp_path.write_text(source, encoding="utf-8")
            json_path.write_text(
                json.dumps(expected, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            written += 1
    print(f"Wrote {written} cases under {HERE}")


if __name__ == "__main__":
    main()
