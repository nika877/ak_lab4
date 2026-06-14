from lang.lexer import LexerToken
from typing import Iterator
from dataclasses import dataclass

from lang.parser.qualname import TreePath

from .step_01_build_tree import step_01_build_tree
from .step_02_analyze_s_expr import  Token_Step_02, step_02_analyze_s_expr
from .step_03_cps import step_03_cps
from .step_04_assign_qualnames import FinalToken, Token_Step_04, step_04_assign_qualnames



@dataclass(slots=True)
class ParserResult:
    file_token: Token_Step_04
    all_tokens: dict[TreePath, FinalToken]


def parse(lexer_iter: Iterator[LexerToken]):
    step = step_01_build_tree(lexer_iter)
    step = step_02_analyze_s_expr(step)
    step = step_03_cps(step)
    print(step.source)

    qn_res = step_04_assign_qualnames(step)

    #all_lambdas = step_05_assign_captures(
    #    qn_res.all_lambdas,
    #    qn_res.all_qualnames
    #)

    return ParserResult(
        qn_res.file_token,
        qn_res.all_tokens
    )
