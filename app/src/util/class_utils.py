from typing import Type


def all_subclasses(cls: Type) -> set[Type]:
    return {cls}.union(s for c in cls.__subclasses__() for s in all_subclasses(c))
