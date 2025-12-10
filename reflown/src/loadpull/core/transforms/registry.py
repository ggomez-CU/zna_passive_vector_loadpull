from __future__ import annotations

from typing import Callable, Dict

TransformFunc = Callable[[dict, dict], dict]


class TransformRegistry:
    """Registry for measurement post-processing callbacks."""

    def __init__(self) -> None:
        self._transforms: Dict[str, TransformFunc] = {}

    def register(self, method: str, func: TransformFunc) -> None:
        self._transforms[method] = func

    def get(self, method: str) -> TransformFunc | None:
        return self._transforms.get(method)

    def apply(self, method: str, payload: dict, cal_cache: dict) -> dict:
        func = self.get(method)
        if not func:
            raise KeyError(f"Transform '{method}' not found in registry")
        return func(payload, cal_cache)
