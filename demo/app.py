"""Entry point for the physically separate public-demo FastAPI assembly."""

from __future__ import annotations

from datetime import timedelta

from backend.observability import emit_event
from backend.server import main as product_main
from backend.settings import RuntimeSettings

from .artifacts import DemoArtifactError, validate_runtime_binding
from .runtime_policy import DemoRuntimePolicy


def main() -> None:
    settings = RuntimeSettings.from_environment()
    data_dir = settings.persistence.data_dir
    app_manifest_path = settings.demo.app_manifest
    try:
        _app_manifest, _seed_manifest = validate_runtime_binding(app_manifest_path, data_dir)
        policy = DemoRuntimePolicy(
            app_manifest_path,
            data_dir / "demo-seed-manifest.json",
            settings=settings,
        )
    except DemoArtifactError as error:
        raise SystemExit(f"Demo artifact validation failed: {error}") from error
    emit_event("runtime", severity="info", signal="demo_seed_validated")
    product_main(
        runtime_policy=policy,
        session_ttl=timedelta(minutes=60),
        settings=settings,
    )


if __name__ == "__main__":
    main()
