from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.inventory_licenses import (
    npm_summary,
    resolve_python_license,
    summarize_python_inventory,
)


class NpmLicenseInventoryTests(unittest.TestCase):
    def test_every_lockfile_package_and_unknown_license_is_inventoried(self) -> None:
        lockfile = {
            "lockfileVersion": 3,
            "packages": {
                "": {"dependencies": {"runtime": "1.0.0"}},
                "node_modules/runtime": {"version": "1.0.0", "license": "MIT"},
                "node_modules/tool": {"version": "2.0.0", "dev": True},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "package-lock.json"
            path.write_text(json.dumps(lockfile), encoding="utf-8")

            summary = npm_summary(path)

        self.assertEqual(2, summary["package_entries"])
        self.assertEqual(["runtime", "tool"], [item["name"] for item in summary["packages"]])
        self.assertEqual(1, summary["review_summary"]["unknown"])
        self.assertEqual("tool", summary["unknown_license_entries"][0]["name"])


class PythonLicenseInventoryTests(unittest.TestCase):
    def test_pep_639_expression_is_used_without_legacy_inference(self) -> None:
        result = resolve_python_license(
            {
                "name": "example",
                "version": "1.0",
                "license_expression": "MIT OR Apache-2.0",
                "license": "ignored",
                "classifiers": [],
            }
        )

        self.assertEqual("MIT OR Apache-2.0", result["license_expression"])
        self.assertEqual("metadata-resolved", result["review_status"])

    def test_unambiguous_legacy_metadata_is_normalized_and_identified(self) -> None:
        result = resolve_python_license(
            {
                "name": "example",
                "version": "1.0",
                "license_expression": None,
                "license": "Apache Software License",
                "classifiers": [],
            }
        )

        self.assertEqual("Apache-2.0", result["license_expression"])
        self.assertEqual("legacy-metadata-resolved", result["review_status"])

    def test_ambiguous_bsd_classifier_remains_an_individual_manual_review(self) -> None:
        result = resolve_python_license(
            {
                "name": "example",
                "version": "1.0",
                "license_expression": None,
                "license": None,
                "classifiers": ["License :: OSI Approved :: BSD License"],
            }
        )

        self.assertIsNone(result["license_expression"])
        self.assertEqual("manual-review-required", result["review_status"])
        self.assertEqual(["unspecified BSD variant"], result["candidates"])

    def test_installed_versions_are_compared_with_uv_lock(self) -> None:
        lockfile = {
            "package": [
                {"name": "lzug", "version": "0.1.0"},
                {"name": "Example_Package", "version": "1.2.3"},
                {"name": "windows-only", "version": "4.0"},
            ]
        }
        installed = {
            "environment": {
                "implementation": "CPython",
                "platform": "linux",
                "python": "3.14.6",
            },
            "packages": [
                {
                    "name": "lzug",
                    "version": "0.1.0",
                    "license_expression": "AGPL-3.0-or-later",
                    "license": None,
                    "classifiers": [],
                },
                {
                    "name": "example-package",
                    "version": "1.2.3",
                    "license_expression": "MIT",
                    "license": None,
                    "classifiers": [],
                },
            ],
        }

        summary = summarize_python_inventory(lockfile, installed)

        self.assertEqual(1, summary["installed_third_party_packages"])
        self.assertEqual("windows-only", summary["locked_but_not_installed"][0]["name"])
        self.assertEqual("AGPL-3.0-or-later", summary["project_distribution"]["license_expression"])

    def test_version_mismatch_fails_closed(self) -> None:
        lockfile = {"package": [{"name": "lzug", "version": "0.1.0"}]}
        installed = {
            "environment": {},
            "packages": [
                {
                    "name": "lzug",
                    "version": "9.9.9",
                    "license_expression": "AGPL-3.0-or-later",
                    "license": None,
                    "classifiers": [],
                }
            ],
        }

        with self.assertRaisesRegex(RuntimeError, "differs from uv.lock"):
            summarize_python_inventory(lockfile, installed)


if __name__ == "__main__":
    unittest.main()
