from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.compose_policy import image_reference_errors, policy_errors

VALID_MODEL = {
    "services": {
        "lzug": {
            "image": "ghcr.io/lxndrp/lzug:1.2.3",
            "user": "10001:10001",
            "read_only": True,
            "restart": "unless-stopped",
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
            "volumes": [{"type": "volume", "source": "lzug_data", "target": "/data"}],
            "healthcheck": {"test": ["CMD", "python", "-m", "backend.healthcheck"]},
            "ports": [{"host_ip": "127.0.0.1", "target": 8000, "published": "8000"}],
            "environment": {
                "LZUG_HTTPS_ONLY": "true",
                "LZUG_CORS_ALLOWED_ORIGINS": "",
                "LZUG_SESSION_TTL_SECONDS": "28800",
                "LZUG_MAX_REQUEST_BYTES": "1048576",
                "LZUG_AUTH_RATE_LIMIT": "20",
                "LZUG_AUTH_RATE_WINDOW_SECONDS": "60",
                "LZUG_MAX_UPLOAD_BYTES": "10485760",
                "LZUG_ALLOWED_UPLOAD_MEDIA_TYPES": (
                    "application/pdf,image/jpeg,image/png,text/plain"
                ),
            },
        }
    }
}


class ComposePolicyTests(unittest.TestCase):
    def test_accepts_semver_and_digest_image_references(self) -> None:
        self.assertEqual(image_reference_errors("lzug:1.2.3-rc.1+build.4"), [])
        self.assertEqual(image_reference_errors(f"lzug@sha256:{'a' * 64}"), [])

    def test_rejects_mutable_placeholder_and_unversioned_images(self) -> None:
        for image in (
            "lzug:latest",
            "REPLACE_IMAGE",
            "lzug:dev",
            "lzug:01.2.3",
            "lzug:1.2.3-01",
            "lzug:1.2.3-0." + "--." * 10_000,
        ):
            with self.subTest(image=image):
                self.assertTrue(image_reference_errors(image))

    def test_accepts_the_complete_lzug_runtime_contract(self) -> None:
        self.assertEqual(policy_errors(VALID_MODEL), [])

    def test_reports_each_changed_runtime_invariant(self) -> None:
        mutations = {
            "user": ("user", "0:0"),
            "read-only": ("read_only", False),
            "capabilities": ("cap_drop", []),
            "socket": ("volumes", ["/var/run/docker.sock:/var/run/docker.sock"]),
            "healthcheck": ("healthcheck", {"test": ["CMD", "curl"]}),
            "ports": ("ports", [{"host_ip": "0.0.0.0"}]),
        }
        for name, (key, value) in mutations.items():
            with self.subTest(name=name):
                model = copy.deepcopy(VALID_MODEL)
                model["services"]["lzug"][key] = value
                self.assertTrue(policy_errors(model))

    def test_cli_returns_a_nonzero_status_with_actionable_output(self) -> None:
        model = copy.deepcopy(VALID_MODEL)
        model["services"]["lzug"]["image"] = "lzug:latest"
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "compose.json"
            config.write_text(json.dumps(model), encoding="utf-8")
            result = subprocess.run(
                ["python3", "scripts/compose_policy.py", str(config)],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("must not use the mutable latest tag", result.stdout)


if __name__ == "__main__":
    unittest.main()
