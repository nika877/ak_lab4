from typing import Any, Type, TypeVar, cast


ExtendT = TypeVar("ExtendT")


def extend_class(self, cls: Type[ExtendT], **fields: Any):
    object.__setattr__(self, "__class__", cls)
    for k, v in fields.items():
        setattr(self, k, v)
    return cast(ExtendT, self)
