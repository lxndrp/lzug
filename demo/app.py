"""Entry point for the physically separate public-demo FastAPI assembly."""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from backend.observability import emit_event
from backend.server import main as product_main

from .artifacts import DemoArtifactError, validate_runtime_binding
from .runtime_policy import DemoRuntimePolicy


def main() -> None:
    data_dir = Path(os.environ.get("LZUG_DATA_DIR", "/data"))
    app_manifest_path = Path(
        os.environ.get("LZUG_DEMO_APP_MANIFEST", "/app/demo-app-manifest.json")
    )
    try:
        _app_manifest, _seed_manifest = validate_runtime_binding(app_manifest_path, data_dir)
        policy = DemoRuntimePolicy(app_manifest_path, data_dir / "demo-seed-manifest.json")
    except DemoArtifactError as error:
        raise SystemExit(f"Demo artifact validation failed: {error}") from error
    emit_event("runtime", severity="info", signal="demo_seed_validated")
    product_main(runtime_policy=policy, session_ttl=timedelta(minutes=60))


if __name__ == "__main__":
    main()
