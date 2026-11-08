from collections.abc import Callable
from importlib import import_module


class Slot[T]:
    def __init__(self) -> None:
        self._value: T | None = None
        self._factory: Callable[[], T] | None = None

    def configure(self, value: T) -> None:
        self._value = value
        self._factory = None

    def provide(self, factory: Callable[[], T]) -> None:
        self._value = None
        self._factory = factory

    def __call__(self) -> T:
        if self._value is None and self._factory is None:
            import_module("app.bootstrap")
        if self._value is None:
            assert self._factory is not None
            self._value = self._factory()
        return self._value
