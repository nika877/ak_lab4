'''
from dataclasses import dataclass
from typing import Generic, Iterable, Iterator, Sequence, cast

from lang.parser.qualname import BuiltinQualName, FileQualName, GenericBuiltinQualName

from .base_token import ParserTokenT
from .extend_class import extend_class
from .step_02_analyze_s_expr import SExpr, SExprDefun, SExprLambda
from .step_04_assign_qualnames import QualName, Token_Step_04


@dataclass
class SExprLambdaWithCaptures(SExprLambda[ParserTokenT], Generic[ParserTokenT]):
    captures: list[FileQualName]


def _step_05_assign_captures(
    lambdas_iter: Iterable[SExprLambda[Token_Step_04]],
    all_qualnames: Iterable[QualName[Token_Step_04, Token_Step_04]]
):
    for lamb in lambdas_iter:
        captures: list[FileQualName] = []
        def traverse(token: Token_Step_04):
            if s_expr := token.try_as_s_expr():
                if _ := s_expr.try_as_file():
                    raise Exception("file token inside lambda captures analyze")

                elif call := s_expr.try_as_call():
                    traverse(call.callee)
                    for arg in call.args:
                        traverse(arg)

                elif defun := s_expr.try_as_defun():
                    traverse(defun.body)

                elif lambda_expr := s_expr.try_as_lambda():
                    traverse(lambda_expr.body)

                elif if_expr := s_expr.try_as_if():
                    traverse(if_expr.cond)
                    traverse(if_expr.branch_t)
                    traverse(if_expr.branch_t)

                elif progn := s_expr.try_as_progn():
                    for st in progn.body:
                        traverse(st)

                else:
                    raise

            elif token.is_ident:
                if _is_builtin := any(
                    qn.symbol.source == token.source
                    for qn in all_qualnames
                    if isinstance(qn, BuiltinQualName)
                ):
                    return

                if _is_generic_builtin := any(
                    qn.source == token.source
                    for qn in all_qualnames
                    if isinstance(qn, GenericBuiltinQualName)
                ):
                    return

                is_alrady_captured = any(
                    capture.decl is token.qualname.decl
                    for capture in captures
                )
                is_lambda_arg = token.qualname.decl is lamb.token
                is_defun_name = any(
                    defun.symbol == token.source
                    for qn in all_qualnames
                    if isinstance(qn, FileQualName)
                    and (defun_s_expr := qn.token.try_as_s_expr())
                    and (defun := defun_s_expr.try_as_defun())
                )

                if not any((is_alrady_captured, is_lambda_arg, is_defun_name)):
                    captures.append(token.qualname)

            elif token.is_integer or token.is_string or token.is_boolean:
                pass

            else:
                raise

        traverse(lamb.token)
        yield cast(
            SExprLambdaWithCaptures[Token_Step_04[FileQualName]],
            extend_class(lamb, SExprLambdaWithCaptures, captures=captures)
        )


def step_05_assign_captures(
    lambdas_iter: Iterable[SExprLambda[Token_Step_04[FileQualName]]],
    all_qualnames: Iterable[QualName[Token_Step_04, Token_Step_04]]
):
    return list(_step_05_assign_captures(lambdas_iter, all_qualnames))
'''
