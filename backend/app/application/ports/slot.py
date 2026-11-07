from importlib import import_module


class Slot[T]:
    def __init__(self) -> None:
        self._value: T | None = None

    def configure(self, value: T) -> None:
        self._value = value

    def __call__(self) -> T:
        if self._value is None:
            import_module("app.bootstrap")
        assert self._value is not None
        return self._value
