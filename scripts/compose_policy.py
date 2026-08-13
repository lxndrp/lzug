#!/usr/bin/env python3

"""Validate only the lzug-specific policy of a rendered Compose model."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SEMVER_IMAGE = re.compile(
    r":(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
DIGEST_IMAGE = re.compile(r"@sha256:[0-9a-fA-F]{64}$")


def image_reference_errors(image: object) -> list[str]:
    if not isinstance(image, str) or not image:
        return ["services.lzug.image must resolve to a non-empty string"]
    if image == "latest" or image.endswith(":latest") or "/latest" in image:
        return ["services.lzug.image must not use the mutable latest tag"]
    if "REPLACE" in image or "<" in image or ">" in image:
        return ["services.lzug.image must not contain a placeholder"]
    if not (SEMVER_IMAGE.search(image) or DIGEST_IMAGE.search(image)):
        return ["services.lzug.image must end in an immutable SemVer tag or sha256 digest"]
    return []


def _volume_targets(volumes: object) -> list[str]:
    if not isinstance(volumes, list):
        return []
    targets: list[str] = []
    for volume in volumes:
        if isinstance(volume, dict) and isinstance(volume.get("target"), str):
            targets.append(volume["target"])
        elif isinstance(volume, str):
            parts = volume.split(":")
            if len(parts) >= 2:
                targets.append(parts[1])
    return targets


def policy_errors(model: object) -> list[str]:
    if not isinstance(model, dict):
        return ["rendered Compose configuration must be an object"]
    services = model.get("services")
    if not isinstance(services, dict) or not isinstance(services.get("lzug"), dict):
        return ["rendered Compose configuration must define services.lzug"]

    service: dict[str, Any] = services["lzug"]
    errors = image_reference_errors(service.get("image"))

    expected = {
        "user": "10001:10001",
        "read_only": True,
        "restart": "unless-stopped",
    }
    for key, value in expected.items():
        if service.get(key) != value:
            errors.append(f"services.lzug.{key} must equal {value!r}")

    if "ALL" not in service.get("cap_drop", []):
        errors.append("services.lzug.cap_drop must contain ALL")
    if "no-new-privileges:true" not in service.get("security_opt", []):
        errors.append("services.lzug.security_opt must enable no-new-privileges")
    if service.get("privileged", False) is not False:
        errors.append("services.lzug.privileged must be false or absent")

    volumes = service.get("volumes", [])
    if "/data" not in _volume_targets(volumes):
        errors.append("services.lzug.volumes must provide /data")
    if any("docker.sock" in str(volume) for volume in volumes):
        errors.append("services.lzug.volumes must not mount a container-engine socket")

    healthcheck = service.get("healthcheck", {})
    test = healthcheck.get("test", []) if isinstance(healthcheck, dict) else []
    if not isinstance(test, list) or test[-3:] != ["python", "-m", "backend.healthcheck"]:
        errors.append("services.lzug.healthcheck must use backend.healthcheck")

    environment = service.get("environment", {})
    required_environment = {
        "LZUG_HTTPS_ONLY": "true",
        "LZUG_CORS_ALLOWED_ORIGINS": {"", None},
        "LZUG_SESSION_TTL_SECONDS": "28800",
        "LZUG_MAX_REQUEST_BYTES": "1048576",
        "LZUG_AUTH_RATE_LIMIT": "20",
        "LZUG_AUTH_RATE_WINDOW_SECONDS": "60",
        "LZUG_MAX_UPLOAD_BYTES": "10485760",
        "LZUG_ALLOWED_UPLOAD_MEDIA_TYPES": "application/pdf,image/jpeg,image/png,text/plain",
    }
    if not isinstance(environment, dict):
        errors.append("services.lzug.environment must be a mapping")
    else:
        for key, value in required_environment.items():
            actual = environment.get(key)
            if isinstance(value, set):
                if actual not in value:
                    errors.append(f"services.lzug.environment.{key} has an unsafe default")
            elif actual != value:
                errors.append(f"services.lzug.environment.{key} must equal {value!r}")

    ports = service.get("ports", [])
    if not isinstance(ports, list) or not ports:
        errors.append("services.lzug.ports must publish a loopback-bound port")
    else:
        for port in ports:
            host_ip = port.get("host_ip") if isinstance(port, dict) else str(port).split(":", 1)[0]
            if host_ip not in {"127.0.0.1", "::1"}:
                errors.append("services.lzug.ports must bind only to loopback")
                break

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    model = json.loads(args.config.read_text(encoding="utf-8"))
    errors = policy_errors(model)
    if errors:
        for error in errors:
            print(f"lzug Compose policy: {error}")
        return 1
    print("lzug Compose policy passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
