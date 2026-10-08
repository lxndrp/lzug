"""Planning domain services with explicit persistence boundaries."""

from __future__ import annotations

from importlib import import_module
from typing import Any


def __getattr__(name: str) -> Any:
    """Resolve proposal exports lazily to keep module dependencies one-way."""
    module = import_module(".proposals", __name__)
    try:
        return getattr(module, name)
    except AttributeError as error:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from error
