"""HTTP entry point for the physically separate public-demo assembly."""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from backend.app import LzugHandler
from backend.app import main as product_main

from .artifacts import DemoArtifactError, validate_runtime_binding
from .runtime_policy import DemoRuntimePolicy


class DemoHandler(LzugHandler):
    """Product HTTP adapter constrained by the public-demo runtime policy."""

    forced_session_ttl = timedelta(minutes=60)


def main() -> None:
    data_dir = Path(os.environ.get("LZUG_DATA_DIR", "/data"))
    app_manifest_path = Path(
        os.environ.get("LZUG_DEMO_APP_MANIFEST", "/app/demo-app-manifest.json")
    )
    try:
        _app_manifest, seed_manifest = validate_runtime_binding(app_manifest_path, data_dir)
        DemoHandler.runtime_policy = DemoRuntimePolicy(
            app_manifest_path, data_dir / "demo-seed-manifest.json"
        )
    except DemoArtifactError as error:
        raise SystemExit(f"Demo artifact validation failed: {error}") from error
    print(f"demo seed revision: {seed_manifest['seed_revision']}")
    product_main(DemoHandler)


if __name__ == "__main__":
    main()
