from __future__ import annotations

import copy
import unittest
from pathlib import Path

from scripts.sbom import (
    CYCLONEDX_SPEC_VERSION,
    DEPENDENCY_SOURCE_NAME,
    cli_command,
    configured_syft_version,
    dependency_command,
    validate_cli,
    validate_dependencies,
    validate_image,
)


def component(name: str, version: str, purl: str, license_id: str | None = None) -> dict:
    value = {"type": "library", "name": name, "version": version, "purl": purl}
    if license_id:
        value["licenses"] = [{"license": {"id": license_id}}]
    return value


def payload(*components: dict, source_name: str = DEPENDENCY_SOURCE_NAME) -> dict:
    return {
        "bomFormat": "CycloneDX",
        "specVersion": CYCLONEDX_SPEC_VERSION,
        "metadata": {
            "tools": {
                "components": [
                    {
                        "type": "application",
                        "name": "syft",
                        "version": configured_syft_version(),
                    }
                ]
            },
            "component": {"type": "application", "name": source_name, "version": "0.1.0"},
        },
        "components": list(components),
    }


class SbomContractTests(unittest.TestCase):
    def test_toolchain_pins_current_syft(self) -> None:
        self.assertEqual("1.51.0", configured_syft_version())

    def test_dependency_generation_uses_standard_format_and_only_agreed_catalogers(self) -> None:
        command = dependency_command(Path("result.cdx.json"), "0.1.0")

        self.assertIn("cyclonedx-json@1.6=result.cdx.json", command)
        catalogers = command[command.index("--override-default-catalogers") + 1]
        self.assertEqual(
            "python-installed-package-cataloger,javascript-lock-cataloger,go-module-file-cataloger",
            catalogers,
        )

    def test_cli_generation_scans_one_already_built_artifact(self) -> None:
        command = cli_command(Path("result.cdx.json"), Path("dist/lzug-admin"), "0.1.0")

        self.assertIn("file:", command[2])
        self.assertTrue(command[2].endswith("/dist/lzug-admin"))
        self.assertIn("cyclonedx-json@1.6=result.cdx.json", command)

    def test_dependency_sbom_covers_python_npm_and_current_go_boundary(self) -> None:
        report = payload(
            component("lzug", "0.1.0", "pkg:pypi/lzug@0.1.0", "AGPL-3.0-or-later"),
            component("Jinja2", "3.1.6", "pkg:pypi/jinja2@3.1.6"),
            component("rxjs", "7.8.2", "pkg:npm/rxjs@7.8.2", "Apache-2.0"),
        )

        summary = validate_dependencies(report, "module example.invalid/lzug\n\ngo 1.26\n")

        self.assertEqual({"npm": 1, "pypi": 2}, summary["purl_types"])
        self.assertEqual(["Jinja2@3.1.6"], summary["python_missing_license_metadata"])
        self.assertEqual("go.mod declares no third-party modules", summary["go_boundary"])

    def test_missing_npm_license_fails_closed(self) -> None:
        report = payload(
            component("lzug", "0.1.0", "pkg:pypi/lzug@0.1.0", "AGPL-3.0-or-later"),
            component("rxjs", "7.8.2", "pkg:npm/rxjs@7.8.2"),
        )

        with self.assertRaisesRegex(ValueError, "npm components without license metadata"):
            validate_dependencies(report, "module example.invalid/lzug\n\ngo 1.26\n")

    def test_declared_go_modules_must_be_present(self) -> None:
        report = payload(
            component("lzug", "0.1.0", "pkg:pypi/lzug@0.1.0", "AGPL-3.0-or-later"),
            component("rxjs", "7.8.2", "pkg:npm/rxjs@7.8.2", "Apache-2.0"),
        )

        with self.assertRaisesRegex(ValueError, "go.mod modules missing"):
            validate_dependencies(
                report,
                "module example.invalid/lzug\n\ngo 1.26\n\nrequire example.invalid/lib v1.0.0\n",
            )

    def test_dependency_sbom_tolerates_main_module_from_concurrent_cli_build(self) -> None:
        report = payload(
            component("lzug", "0.1.0", "pkg:pypi/lzug@0.1.0", "AGPL-3.0-or-later"),
            component("rxjs", "7.8.2", "pkg:npm/rxjs@7.8.2", "Apache-2.0"),
            component(
                "github.com/lxndrp/lzug/operator-cli",
                "UNKNOWN",
                "pkg:golang/github.com/lxndrp/lzug/operator-cli",
            ),
            component("stdlib", "go1.26.5", "pkg:golang/stdlib@1.26.5"),
        )

        summary = validate_dependencies(
            report, "module github.com/lxndrp/lzug/operator-cli\n\ngo 1.26\n"
        )

        self.assertEqual("go.mod declares no third-party modules", summary["go_boundary"])

    def test_cli_sbom_requires_main_module_runtime_and_declared_dependencies(self) -> None:
        report = payload(
            component(
                "github.com/lxndrp/lzug/operator-cli",
                "UNKNOWN",
                "pkg:golang/github.com/lxndrp/lzug/operator-cli",
            ),
            component("stdlib", "go1.26.5", "pkg:golang/stdlib@1.26.5"),
            source_name="lzug-admin-linux-amd64",
        )
        report["metadata"]["component"]["type"] = "file"

        summary = validate_cli(report, "module github.com/lxndrp/lzug/operator-cli\n\ngo 1.26\n")

        self.assertEqual("lzug-admin-linux-amd64", summary["artifact"])
        self.assertEqual(2, summary["go_components"])

    def test_image_sbom_excludes_build_only_ecosystems(self) -> None:
        report = payload(
            component("sqlalchemy", "2.0.51", "pkg:pypi/sqlalchemy@2.0.51", "MIT"),
            component("base-files", "12.4", "pkg:deb/debian/base-files@12.4"),
            source_name="lzug-ci:example",
        )

        summary = validate_image(report)

        self.assertEqual({"deb": 1, "pypi": 1}, summary["purl_types"])

        invalid = copy.deepcopy(report)
        invalid["components"].append(component("rxjs", "7.8.2", "pkg:npm/rxjs@7.8.2", "Apache-2.0"))
        with self.assertRaisesRegex(ValueError, "build-only ecosystems"):
            validate_image(invalid)


if __name__ == "__main__":
    unittest.main()
