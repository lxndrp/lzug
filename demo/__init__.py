"""Demo-only assembly code excluded from the canonical product image."""

from __future__ import annotations

import sys
from pathlib import Path

_backend_source = Path(__file__).resolve().parents[1] / "backend" / "src"
if _backend_source.is_dir() and str(_backend_source) not in sys.path:
    sys.path.insert(0, str(_backend_source))
