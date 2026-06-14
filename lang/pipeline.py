"""
Точка входа компиляции текста в байткод
"""

from __future__ import annotations

from io import StringIO

from lang.compiler import CompilationResult, Compiler
from lang.compiler.inferrer import infer
from lang.lexer import tokenize
from lang.parser import ParserResult, assign_qualnames, cps_transform, parse
from lang.runtime import interpret


def compile_source(source: str) -> CompilationResult:
    parsed = parse(tokenize(source))

    inferred_semantic = infer(parsed, use_semantic_types=True)
    cps_storage = cps_transform(inferred_semantic.storage)
    cps_qn = assign_qualnames(cps_storage)
    cps_result = ParserResult(
        cps_qn.storage,
        cps_qn.all_tokens,
        cps_qn.mutable_paths,
        cps_qn.autoboxed_paths,
    )
    inferred = infer(cps_result, use_semantic_types=False)

    return Compiler.compile(inferred)


def run_source(
    source: str,
    input_data: list[int] | None = None,
    output_stream: StringIO | None = None,
) -> tuple[int, str, list[str]]:
    compiled = compile_source(source)
    return interpret(
        compiled.bytecode,
        compiled.entry_point,
        input_data=input_data,
        output_stream=output_stream,
    )
