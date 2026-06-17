"""Квалифицированные имена (QualName) и пути в дереве программы (TreePath).

Каждый узел программы имеет уникальный путь, например:
  file.st1.[square].x — параметр x в функции square

Типы имён:
  DefinitionQualName — определение (defun, lambda, let-подобное)
  UsageQualName      — использование переменной (ссылка на definition)
  BuiltinQualName    — встроенная функция (+, print, input...)
  ProjectionQualName — захваченная переменная в замыкании
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from ctypes import c_double, c_float, c_int32, c_uint32
from dataclasses import dataclass
from typing import Any, Literal, Protocol, overload, override

from lang.compiler.bytecode import BytecodeUnit
from lang.exceptions import InferrerError
from lang.lang_type import (
    FunctionLanguageType,
    InferableLanguageType,
    LanguageType,
    LanguageTypeVar,
    PrimitiveLanguageType,
    SubstitutionMap,
)


@dataclass(slots=True, frozen=True)
class TreePathEntry:
    string: str
    is_scope: bool

    def __str__(self):
        return self.string

    def as_entire_tree_path(self):
        return TreePath((self,))

    @staticmethod
    def for_file():
        return TreePathEntry("file", False)

    @staticmethod
    def for_body():
        return TreePathEntry("body", False)

    @staticmethod
    def for_if():
        return TreePathEntry("if", False)

    @staticmethod
    def for_cond():
        return TreePathEntry("cond", False)

    @staticmethod
    def for_branch_t():
        return TreePathEntry("t", False)

    @staticmethod
    def for_branch_f():
        return TreePathEntry("f", False)

    @staticmethod
    def for_progn():
        return TreePathEntry("progn", False)

    @staticmethod
    def for_const(source: str):
        return TreePathEntry(f"const.{source}", False)

    @staticmethod
    def for_ident(source: str):
        return TreePathEntry(source, False)

    @staticmethod
    def for_statement(index: int):
        return TreePathEntry(f"st{index + 1}", False)

    @staticmethod
    def for_call_arg(index: int):
        return TreePathEntry(f"arg{index + 1}", False)

    @staticmethod
    def for_scope(source: str):
        return TreePathEntry(f"[{source}]", True)

    @staticmethod
    def for_anon_call():
        return TreePathEntry("()", False)

    @staticmethod
    def for_named_call(callee_source: str):
        return TreePathEntry(f"({callee_source})", False)

    @staticmethod
    def for_builtin(source: str):
        return TreePathEntry(f"{{{source}}}", False)

    @staticmethod
    def for_projection(path: TreePath, projection_scope: TreePath):
        return TreePathEntry(f"proj{{{path} in {projection_scope}}}", False)

    @staticmethod
    def for_usage(path: TreePath, definition_path: TreePath):
        return TreePathEntry(f"usage{{{path} of {definition_path}}}", False)


@dataclass(slots=True, frozen=True)
class TreePath:
    """Уникальный путь к узлу в дереве (цепочка TreePathEntry)."""

    entries: tuple[TreePathEntry, ...]

    def __str__(self):
        return ".".join(map(str, self.entries))

    def combine(self, entry: TreePathEntry):
        new_entries = tuple(list(self.entries) + [entry])
        return TreePath(new_entries)

    def next_nearest_scope(self):
        scope_indices = [i for i, entry in enumerate(self.entries) if entry.is_scope]

        if len(scope_indices) < 2:
            return None

        parent_idx = scope_indices[-2]
        return TreePath(self.entries[: parent_idx + 1])

    def replace_leaf(self, new_entry: TreePathEntry):
        new_entries = list(self.entries)
        new_entries[-1] = new_entry
        return TreePath(tuple(new_entries))

    @staticmethod
    def from_single_entry(entry: TreePathEntry):
        return TreePath((entry,))


@dataclass
class BaseQualName(ABC):
    @property
    @abstractmethod
    def is_builtin(self) -> bool: ...

    @property
    @abstractmethod
    def path(self) -> TreePath: ...


class LanguageTypeVarEmitter(Protocol):
    def __call__(self) -> LanguageTypeVar: ...


class LanguageTypeBuilder(Protocol):
    def __call__(
        self, typevar_emitter: LanguageTypeVarEmitter
    ) -> LanguageType | InferableLanguageType: ...


class InplaceBytecodeEmitter(Protocol):
    def __call__(self, unit: BytecodeUnit, slot: int, *args: int) -> Any: ...


@dataclass
class LambdaEmitter:
    slots: list[str]
    bytecode_emitter: LambdaBytecodeEmitter


class LambdaBytecodeEmitter(Protocol):
    def __call__(self, unit: BytecodeUnit, slots: list[int], k: int, *args: int) -> Any: ...


@dataclass
class BuiltinSymbol:
    source: str
    path: TreePath
    lang_type_builder: LanguageTypeBuilder
    emit_inplace: InplaceBytecodeEmitter | None
    emit_lambda: LambdaEmitter | None

    def __post_init__(self):
        assert self.emit_inplace or self.emit_lambda

    @property
    def is_atomic(self):
        return self.emit_lambda is None

    @property
    def semantic_lang_type_builder(self) -> LanguageTypeBuilder:
        if self.is_atomic:
            return self.lang_type_builder

        def builder(
            typevar_emitter: LanguageTypeVarEmitter,
        ) -> LanguageType | InferableLanguageType:
            full_type = self.lang_type_builder(typevar_emitter)
            assert isinstance(full_type, FunctionLanguageType)
            last_arg = full_type.arg_types[-1]
            if isinstance(last_arg, FunctionLanguageType):
                semantic_return_type = last_arg.arg_types[0]
                semantic_args = list(full_type.arg_types[:-1])
                return FunctionLanguageType(semantic_args, semantic_return_type)
            else:
                return full_type

        return builder


@dataclass
class BuiltinSymbolOverload:
    lang_type: LanguageType | InferableLanguageType
    symbol: BuiltinSymbol


class GenericBuiltinSymbolBuilderProtocol(Protocol):
    def __call__(
        self, typevar_emitter: LanguageTypeVarEmitter, use_semantic_types: bool = True
    ) -> GenericBuiltinSymbol: ...


@dataclass
class GenericBuiltinSymbol:
    source: str
    overloads: list[BuiltinSymbolOverload]

    def __post_init__(self):
        assert len(self.overloads) > 0
        self.source = self.overloads[0].symbol.source
        for o in self.overloads:
            assert self.source == o.symbol.source

    @overload
    def resolve_override(
        self,
        inferred_type: LanguageType | InferableLanguageType,
        subm: SubstitutionMap,
        is_soft: Literal[True],
    ) -> BuiltinSymbolOverload | None: ...

    @overload
    def resolve_override(
        self,
        inferred_type: LanguageType | InferableLanguageType,
        subm: SubstitutionMap,
        is_soft: Literal[False],
    ) -> BuiltinSymbolOverload: ...

    def resolve_override(
        self,
        inferred_type: LanguageType | InferableLanguageType,
        subm: SubstitutionMap,
        is_soft: bool,
    ) -> BuiltinSymbolOverload | None:
        compatible_overloads: list[BuiltinSymbolOverload] = []
        exact_overloads: list[BuiltinSymbolOverload] = []

        for o in self.overloads:
            if GenericBuiltinSymbol.is_compatible(inferred_type, o.lang_type, subm):
                compatible_overloads.append(o)
                if GenericBuiltinSymbol.is_exact_match(inferred_type, o.lang_type, subm):
                    exact_overloads.append(o)

        if len(exact_overloads) == 1:
            return exact_overloads[0]
        elif len(exact_overloads) > 1:
            if is_soft:
                return None
            raise InferrerError(
                f"Multiple exact overloads for {self.source} match type {inferred_type}"
            )

        if len(compatible_overloads) == 0:
            if is_soft:
                return None
            raise InferrerError(f"No overload for {self.source} matches type {inferred_type}")
        if len(compatible_overloads) > 1:
            if is_soft:
                return None
            raise InferrerError(f"Multiple overloads for {self.source} match type {inferred_type}")
        return compatible_overloads[0]

    @staticmethod
    def is_compatible(
        inferred: LanguageType | InferableLanguageType,
        target: LanguageType | InferableLanguageType,
        subm: SubstitutionMap,
    ) -> bool:
        inferred = inferred.deref(subm)
        target = target.deref(subm)

        if isinstance(inferred, LanguageTypeVar):
            return True
        if isinstance(target, LanguageTypeVar):
            return True

        if isinstance(inferred, FunctionLanguageType) and isinstance(target, FunctionLanguageType):
            if len(inferred.arg_types) != len(target.arg_types):
                return False

            args_match = all(
                GenericBuiltinSymbol.is_compatible(a, b, subm)
                for a, b in zip(inferred.arg_types, target.arg_types, strict=True)
            )
            return args_match and GenericBuiltinSymbol.is_compatible(
                inferred.return_type, target.return_type, subm
            )

        return inferred.is_same(target, subm)

    @staticmethod
    def is_exact_match(
        inferred: LanguageType | InferableLanguageType,
        target: LanguageType | InferableLanguageType,
        subm: SubstitutionMap,
    ) -> bool:
        """Check if types match exactly without any typevars (more specific than is_compatible)."""
        inferred = inferred.deref(subm)
        target = target.deref(subm)

        if isinstance(inferred, LanguageTypeVar) or isinstance(target, LanguageTypeVar):
            return False

        if isinstance(inferred, FunctionLanguageType) and isinstance(target, FunctionLanguageType):
            if len(inferred.arg_types) != len(target.arg_types):
                return False

            args_exact = all(
                GenericBuiltinSymbol.is_exact_match(a, b, subm)
                for a, b in zip(inferred.arg_types, target.arg_types, strict=True)
            )
            return args_exact and GenericBuiltinSymbol.is_exact_match(
                inferred.return_type, target.return_type, subm
            )

        return inferred.is_same(target, subm)


@dataclass
class ProjectionQualName(BaseQualName):
    tree_path: TreePath
    definition_path: TreePath
    projection_scope: TreePath

    @property
    @override
    def is_builtin(self) -> bool:
        return False

    @property
    @override
    def path(self) -> TreePath:
        return self.tree_path


@dataclass
class BaseConstQualName(BaseQualName):
    tree_path: TreePath
    source: str

    @property
    @override
    def is_builtin(self) -> bool:
        return False

    @property
    @override
    def path(self) -> TreePath:
        return self.tree_path

    @property
    @abstractmethod
    def language_type(self) -> LanguageType: ...


@dataclass
class IntegerConstQualName(BaseConstQualName):
    const: c_int32

    @property
    @override
    def language_type(self) -> LanguageType:
        return PrimitiveLanguageType.INTEGER


@dataclass
class BooleanConstQualName(BaseConstQualName):
    const: bool

    @property
    @override
    def language_type(self) -> LanguageType:
        return PrimitiveLanguageType.BOOLEAN


@dataclass
class FloatConstQualName(BaseConstQualName):
    const: c_float

    @property
    @override
    def language_type(self) -> LanguageType:
        return PrimitiveLanguageType.FLOAT


@dataclass
class DoubleConstQualName(BaseConstQualName):
    const: c_double

    @property
    @override
    def language_type(self) -> LanguageType:
        return PrimitiveLanguageType.DOUBLE


@dataclass
class StringConstQualName(BaseConstQualName):
    const: list[c_uint32]

    @property
    @override
    def language_type(self) -> LanguageType:
        return PrimitiveLanguageType.STRING


@dataclass
class BuiltinQualName(BaseQualName):
    symbol: BuiltinSymbol

    @property
    @override
    def is_builtin(self) -> bool:
        return True

    @property
    @override
    def path(self) -> TreePath:
        return self.symbol.path


@dataclass
class GenericBuiltinQualName(BaseQualName):
    tree_path: TreePath
    symbol_builder: GenericBuiltinSymbolBuilderProtocol

    @property
    @override
    def is_builtin(self) -> bool:
        return True

    @property
    @override
    def path(self) -> TreePath:
        return self.tree_path


@dataclass
class DefinitionQualName(BaseQualName):
    tree_path: TreePath

    @property
    @override
    def is_builtin(self) -> bool:
        return False

    @property
    @override
    def path(self) -> TreePath:
        return self.tree_path


@dataclass
class UsageQualName(BaseQualName):
    tree_path: TreePath
    definition_path: TreePath

    @property
    @override
    def is_builtin(self) -> bool:
        return False

    @property
    @override
    def path(self) -> TreePath:
        return self.tree_path


type ConstQualName = (
    IntegerConstQualName
    | BooleanConstQualName
    | FloatConstQualName
    | DoubleConstQualName
    | StringConstQualName
)


type QualName = (
    ProjectionQualName
    | BuiltinQualName
    | GenericBuiltinQualName
    | DefinitionQualName
    | UsageQualName
    | BaseConstQualName
)
