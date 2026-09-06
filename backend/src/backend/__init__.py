"""Small server package for the first persistent lzug backend."""

from __future__ import annotations

from pathlib import Path

# Keep the component-owned test helpers importable during repository tests
# without adding them to the runtime wheel.
_component_root = Path(__file__).resolve().parents[2]
if (_component_root / "tests").is_dir():
    __path__.append(str(_component_root))
