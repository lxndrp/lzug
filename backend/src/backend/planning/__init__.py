"""Planning domain services.

The candidate-day pilot stays importable without the legacy ORM-backed planning
service. Other planning exports are loaded only when a caller requests them.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


def __getattr__(name: str) -> Any:
    """Resolve legacy planning exports without loading them for every submodule."""
    module = import_module("._legacy_service", __name__)
    try:
        return getattr(module, name)
    except AttributeError as error:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from error
