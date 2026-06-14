from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar, Generic, Literal, Sequence, TypeVar, assert_never, override


@dataclass
class UnificationError:
    message: str
    cause: UnificationError | None = None


@dataclass
class UnificationPass:
    lang_type: LanguageType | InferableLanguageType
    was_unified: bool


type UnificationResult = UnificationPass | UnificationError
type SubstitutionMap = dict[str, LanguageType | InferableLanguageType]


@dataclass(frozen=True)
class BaseLanguageType(ABC):
    @abstractmethod
    def is_same(self, other: LanguageType | InferableLanguageType, subm: SubstitutionMap) -> bool:
        ...

    @abstractmethod
    def __str__(self) -> str:
        ...

    @abstractmethod
    def unify(self, other: LanguageType | InferableLanguageType, subm: SubstitutionMap) -> UnificationResult:
        ...

    @abstractmethod
    def is_complete(self, subm: SubstitutionMap) -> bool:
        ...

    def deref(self, subm: SubstitutionMap) -> LanguageType | InferableLanguageType:
        assert isinstance(self, (PrimitiveLanguageType, FunctionLanguageType, LanguageTypeVar))
        t = self
        seen = set()
        while isinstance(t, LanguageTypeVar) and t.name in subm:
            tid = id(t)
            if tid in seen:
                break
            seen.add(tid)
            t = subm[t.name]
        return t

    @abstractmethod
    def complete(self, subm: SubstitutionMap) -> LanguageType | None:
        ...

    def occurs_in(self, target: LanguageType | InferableLanguageType, subm: SubstitutionMap) -> bool:
        self_d = self.deref(subm)
        target_d = target.deref(subm)

        if self_d.is_same(target_d, subm):
            return False

        return self_d._occurs_in_recursive(target_d, subm)

    def _occurs_in_recursive(self, target_d, subm) -> bool:
        self_d = self.deref(subm)
        target_d = target_d.deref(subm)

        if self_d.is_same(target_d, subm):
            return True

        if isinstance(target_d, FunctionLanguageType):
            return any(self_d._occurs_in_recursive(a, subm) for a in target_d.arg_types) or \
                   self_d._occurs_in_recursive(target_d.return_type, subm)

        return False

LanguageTypeT = TypeVar(
    "LanguageTypeT",
    bound="LanguageType | InferableLanguageType",
    covariant=True
)


PrimitiveLanguageTypeKind = Literal["VOID", "INTEGER", "FLOAT", "BOOLEAN", "STRING"]

@dataclass(frozen=True)
class PrimitiveLanguageType(BaseLanguageType):
    VOID: ClassVar["PrimitiveLanguageType"]
    INTEGER: ClassVar["PrimitiveLanguageType"]
    FLOAT: ClassVar["PrimitiveLanguageType"]
    BOOLEAN: ClassVar["PrimitiveLanguageType"]
    STRING: ClassVar["PrimitiveLanguageType"]

    _kind: PrimitiveLanguageTypeKind

    @property
    def kind(self):
        return self._kind

    @override
    def is_same(self, other: LanguageType | InferableLanguageType, subm: SubstitutionMap):
        other_d = other.deref(subm)
        if isinstance(other_d, PrimitiveLanguageType):
            return self.kind == other_d.kind
        return False

    @override
    def __str__(self) -> str:
        return self.kind

    @override
    def unify(self, other: LanguageType | InferableLanguageType, subm: SubstitutionMap):
        other_d = other.deref(subm)
        if isinstance(other_d, PrimitiveLanguageType):
            if self.is_same(other_d, subm):
                return UnificationPass(self, False)
            return UnificationError(f"{self} != {other_d}")
        if isinstance(other_d, FunctionLanguageType):
            return UnificationError(f"{self} != {other_d}")
        elif isinstance(other_d, LanguageTypeVar):
            subm[other_d.name] = self
            return UnificationPass(self, True)
        else:
            assert_never(other_d)

    @override
    def is_complete(self, subm: SubstitutionMap):
        return True

    @override
    def complete(self, subm: SubstitutionMap):
        return self


@dataclass(frozen=True)
class FunctionLanguageType(BaseLanguageType, Generic[LanguageTypeT]):
    _arg_types: Sequence[LanguageTypeT]
    _return_type: LanguageTypeT

    @property
    def arg_types(self):
        return self._arg_types

    @property
    def return_type(self):
        return self._return_type

    @override
    def is_same(self, other: LanguageType | InferableLanguageType, subm: SubstitutionMap):
        other_d = other.deref(subm)
        if isinstance(other_d, FunctionLanguageType):
            return (
                self.return_type.is_same(other_d.return_type, subm)
                and
                len(self.arg_types) == len(other_d.arg_types)
                and
                all(a.is_same(b, subm) for a, b in zip(self.arg_types, other_d.arg_types))
            )
        return False

    @override
    def __str__(self) -> str:
        return f"FUNC[{' '.join(map(lambda a: str(a), self.arg_types))} -> {self.return_type}]"

    @override
    def unify(self, other: LanguageType | InferableLanguageType, subm: SubstitutionMap) -> UnificationResult:
        other_d = other.deref(subm)
        if isinstance(other_d, PrimitiveLanguageType):
            return UnificationError(f"FUNC != {other_d.kind}")
        if isinstance(other_d, FunctionLanguageType):
            if self.is_same(other_d, subm):
                return UnificationPass(self, False)
            if len(self.arg_types) != len(other_d.arg_types):
                return UnificationError(f"arity mismatch: {self} != {other_d}")

            new_arg_types: list[LanguageType | InferableLanguageType] = []
            was_unified = False
            for a, b in zip(self.arg_types, other_d.arg_types):
                if isinstance(unified := a.unify(b, subm), UnificationError):
                    return UnificationError(f"{self} != {other_d}", cause=unified)
                new_arg_types.append(unified.lang_type)
                was_unified |= unified.was_unified

            if isinstance(new_return_type := self.return_type.unify(other_d.return_type, subm), UnificationError):
                return UnificationError(f"{self} != {other_d}", cause=new_return_type)
            was_unified |= new_return_type.was_unified

            if self.occurs_in(other_d, subm):
                return UnificationError(f"recursive type {self} occurs in {other_d}")
            if other_d.occurs_in(self, subm):
                return UnificationError(f"recursive type {other_d} occurs in {self}")

            return UnificationPass(FunctionLanguageType(
                new_arg_types,
                new_return_type.lang_type
            ), was_unified)
        elif isinstance(other_d, LanguageTypeVar):
            subm[other_d.name] = self
            return UnificationPass(self, True)
        else:
            assert_never(other_d)

    @override
    def is_complete(self, subm: SubstitutionMap):
        return (
            all(arg.is_complete(subm) for arg in self.arg_types)
            and self.return_type.is_complete(subm)
        )

    @override
    def complete(self, subm: SubstitutionMap) -> LanguageType | None:
        new_args: list[LanguageType] = []
        for arg in self.arg_types:
            if (new_arg := arg.complete(subm)) is None:
                return None
            new_args.append(new_arg)
        if (new_rt := self.return_type.complete(subm)) is None:
            return None
        return FunctionLanguageType(new_args, new_rt)


@dataclass(frozen=True)
class LanguageTypeVar(BaseLanguageType):
    _name: str

    @property
    def name(self):
        return self._name

    @override
    def is_same(self, other: LanguageType | InferableLanguageType, subm: SubstitutionMap):
        self_d = self.deref(subm)
        other_d = other.deref(subm)
        if isinstance(self_d, LanguageTypeVar) and isinstance(other_d, LanguageTypeVar):
            return self_d.name == other_d.name
        return False

    @override
    def __str__(self) -> str:
        return self.name

    @override
    def unify(self, other: LanguageType | InferableLanguageType, subm: SubstitutionMap) -> UnificationResult:
        other_d = other.deref(subm)
        if isinstance(other_d, (PrimitiveLanguageType, FunctionLanguageType)):
            return other_d.unify(self, subm)
        elif isinstance(other_d, LanguageTypeVar):
            if self.is_same(other_d, subm):
                return UnificationPass(self, False)
            subm[other_d.name] = self
            return UnificationPass(self, True)
        else:
            assert_never(other_d)

    @override
    def is_complete(self, subm: SubstitutionMap):
        return not isinstance(self.deref(subm), LanguageTypeVar)

    @override
    def complete(self, subm: SubstitutionMap) -> LanguageType | None:
        self_d = self.deref(subm)
        if isinstance(self_d, PrimitiveLanguageType):
            return self_d
        if isinstance(self_d, FunctionLanguageType):
            return self_d.complete(subm)
        return None

type LanguageType = (
    PrimitiveLanguageType | FunctionLanguageType["LanguageType"]
)
type InferableLanguageType = (
    PrimitiveLanguageType | FunctionLanguageType["InferableLanguageType"] | LanguageTypeVar
)


PrimitiveLanguageType.VOID = PrimitiveLanguageType("VOID")
PrimitiveLanguageType.INTEGER = PrimitiveLanguageType("INTEGER")
PrimitiveLanguageType.FLOAT = PrimitiveLanguageType("FLOAT")
PrimitiveLanguageType.STRING = PrimitiveLanguageType("STRING")
PrimitiveLanguageType.BOOLEAN = PrimitiveLanguageType("BOOLEAN")
