"""Встроенные функции языка (stdlib).

Каждая встроенная описана как BuiltinSymbol: имя, тип, способ генерации
байткода (emit_lambda — отдельный фрагмент кода, emit_inplace — вставка
в месте вызова для «атомарных» операций вроде + для целых).

Модули по категориям: integers, floats, doubles, strings, io, logic.
"""

from dataclasses import dataclass
from typing import Protocol

from lang.parser.qualname import (
    BuiltinQualName,
    BuiltinSymbol,
    BuiltinSymbolOverload,
    GenericBuiltinSymbol,
    GenericBuiltinSymbolBuilderProtocol,
    LanguageTypeVarEmitter,
    TreePath,
    TreePathEntry,
)

from .doubles import builtin_doubles
from .floats import builtin_floats
from .integers import builtin_integers
from .io import builtin_io
from .logic import builtin_logic
from .strings import builtin_strings


class BuiltinQualNameInstantiator(Protocol):
    def __call__(self) -> BuiltinQualName: ...


@dataclass(frozen=True)
class GenericBuiltinSymbolBuilder(GenericBuiltinSymbolBuilderProtocol):
    source: str
    path: TreePath
    entries: list[BuiltinSymbol]

    def __post_init__(self):
        assert len(self.entries) > 0

    def __call__(
        self, typevar_emitter: LanguageTypeVarEmitter, use_semantic_types: bool = True
    ) -> GenericBuiltinSymbol:
        source = self.entries[0].source
        overloads = []

        for entry in self.entries:
            assert source == entry.source
            if use_semantic_types:
                lt = entry.semantic_lang_type_builder(typevar_emitter)
            else:
                lt = entry.lang_type_builder(typevar_emitter)
            overloads.append(BuiltinSymbolOverload(lt, entry))

        return GenericBuiltinSymbol(source, overloads)


def builtin_symbols() -> list[BuiltinSymbol]:
    """Все нетипизированные (не generic) встроенные: +, <, input, concat..."""
    return [
        *builtin_logic(),
        *builtin_integers(),
        *builtin_floats(),
        *builtin_doubles(),
        *builtin_strings(),
        *builtin_io(),
    ]


def generic_builtin_symbols_builders() -> list[GenericBuiltinSymbolBuilder]:
    """Перегруженные встроенные: +, print, to-string с разными типами."""
    from .doubles import (
        builtin_add_double,
        builtin_to_double_from_integer,
        builtin_to_integer_from_double,
        builtin_to_string_double,
    )
    from .floats import (
        builtin_to_float_from_integer,
        builtin_to_integer_from_float,
        builtin_to_string_float,
    )
    from .integers import (
        builtin_add_integer_2,
        builtin_add_integer_3,
        builtin_to_string_integer,
    )
    from .io import builtin_print_string
    from .strings import builtin_add_string

    return [
        GenericBuiltinSymbolBuilder(
            "+",
            TreePathEntry.for_builtin("+<T>").as_entire_tree_path(),
            [
                builtin_add_integer_2(),
                builtin_add_integer_3(),
                builtin_add_double(),
                builtin_add_string(),
            ],
        ),
        GenericBuiltinSymbolBuilder(
            "print",
            TreePathEntry.for_builtin("print<T>").as_entire_tree_path(),
            [
                builtin_print_string(),
            ],
        ),
        GenericBuiltinSymbolBuilder(
            "to-string",
            TreePathEntry.for_builtin("to-string<T>").as_entire_tree_path(),
            [
                builtin_to_string_integer(),
                builtin_to_string_float(),
                builtin_to_string_double(),
            ],
        ),
        GenericBuiltinSymbolBuilder(
            "to-integer",
            TreePathEntry.for_builtin("to-integer<T>").as_entire_tree_path(),
            [
                builtin_to_integer_from_float(),
                builtin_to_integer_from_double(),
            ],
        ),
        GenericBuiltinSymbolBuilder(
            "to-float",
            TreePathEntry.for_builtin("to-float<T>").as_entire_tree_path(),
            [
                builtin_to_float_from_integer(),
            ],
        ),
        GenericBuiltinSymbolBuilder(
            "to-double",
            TreePathEntry.for_builtin("to-double<T>").as_entire_tree_path(),
            [
                builtin_to_double_from_integer(),
            ],
        ),
    ]


def find_builtin_symbol(source: str):
    """Найти встроенную по имени (+, -, input...)."""
    for symbol in builtin_symbols():
        if symbol.source == source:
            return symbol
    return None


def find_generic_builtin_symbol_builder(source: str):
    """Найти перегружаемую встроенную (print, to-string...)."""
    for builder in generic_builtin_symbols_builders():
        if builder.source == source:
            return builder
    return None


"""
now we face severe problem. we would like to implement float and doubles arithmetic with generic overloads of +<T>, -<T>, etc. (together with
  integers). but the issue is that it is either hard or impossible to implement as atomic operation - due to using only integers-opcodes (we cannot add
   floating). and thats the main reason why string addition is done via 'concat' and not '+' - same issue: string addition is not atomic, but we treat
  '+' as atomic. and atomic calls do not carry the CPS-transformation (that would be required to implement 'concat' or +<float> or +<double> as
  function). so when CPS-transformer sees '+', it does not yet know whether it would be an atomic integer addition, or function call. also issue with
  inferrer - it inferres types only after CPS. so instead of seeing type mismatch report with original code, user sees it with internally modified
  output, with continuations and such. so options: 1) it is to difficult to change anything, so we would make add-float, add-double etc. (unpreffered)
  or 2) (preferred) apply inferrer before CPS, then CPS would know how to transform anything. maybe then make CPSTransformer carry types, or maybe just
   let it rebuilt tree and apply inferrer again under the invariant that CPSTransformer didnt change types (and it should not). if we do this, perhaps
  we need 2 builtins: one with no continuation in its type definition (so (print 123) would not complain that it requires a second argument as
  continuation - before CPS). and then names like '#print', that are internal only. they would be constructed during CPS and have a continuation last
  param. or maybe we even modify FunctionLanguageType to have optional continuation slot instead of handling it inside arglist and make generics like
  FunctionLanguageType[None] = no continuation (type before CPS), FunctionLanguageType[LanguageType] = has continuation slot. (then
  CPSFunctionLanguageType
"""
