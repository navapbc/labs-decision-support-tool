from typing import Type, TypeVar

T = TypeVar("T")


def all_subclasses(cls: Type[T]) -> set[Type[T]]:
    return {cls}.union(s for c in cls.__subclasses__() for s in all_subclasses(c))
