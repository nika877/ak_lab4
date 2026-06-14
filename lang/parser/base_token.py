from dataclasses import dataclass
from typing import Any, Generic, Type, TypeVar

from .extend_class import ExtendT, extend_class


ParserTokenT = TypeVar("ParserTokenT", bound="ParserToken")

@dataclass
class ParserToken(Generic[ParserTokenT]):
    def extend(self, cls: Type[ExtendT], **fields: Any):
        return extend_class(self, cls, **fields)
