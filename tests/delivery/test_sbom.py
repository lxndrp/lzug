from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.sbom import (
    CYCLONEDX_SPEC_VERSION,
    DEPENDENCY_SOURCE_NAME,
    aggregate_release_sbom,
    cli_command,
    cli_modules,
    configured_syft_version,
    dependency_command,
    go_module_contract,
    go_module_graph,
    validate_cli,
    validate_dependencies,
    validate_image,
    validate_release,
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
    def test_release_inventory_includes_the_official_age_module(self) -> None:
        main, required = go_module_contract(Path("operator-cli/go.mod").read_text(encoding="utf-8"))

        self.assertEqual("github.com/lxndrp/lzug/operator-cli", main)
        self.assertIn("filippo.io/age", required)

    def test_dependency_generation_uses_standard_format_and_only_agreed_catalogers(self) -> None:
        command = dependency_command(Path("result.cdx.json"), "0.1.0")

        self.assertEqual("syft", command[0])
        self.assertIn("cyclonedx-json@1.6=result.cdx.json", command)
        self.assertIn("./backend/src/lzug.egg-info/**", command)
        catalogers = command[command.index("--override-default-catalogers") + 1]
        self.assertEqual(
            "python-installed-package-cataloger,javascript-lock-cataloger,go-module-file-cataloger",
            catalogers,
        )

    def test_cli_generation_scans_one_already_built_artifact(self) -> None:
        command = cli_command(Path("result.cdx.json"), Path("dist/lzug-admin"), "0.1.0")

        self.assertEqual("syft", command[0])
        self.assertIn("file:", command[2])
        self.assertTrue(command[2].endswith("/dist/lzug-admin"))
        self.assertIn("cyclonedx-json@1.6=result.cdx.json", command)

    def test_dependency_sbom_covers_python_npm_and_current_go_boundary(self) -> None:
        report = payload(
            component("lzug", "0.1.0", "pkg:pypi/lzug@0.1.0", "AGPL-3.0-or-later"),
            component("Jinja2", "3.1.6", "pkg:pypi/jinja2@3.1.6"),
            component("rxjs", "7.8.2", "pkg:npm/rxjs@7.8.2", "Apache-2.0"),
        )

        summary = validate_dependencies(report, "module example.invalid/lzug\n\ngo 1.26\n", set())

        self.assertEqual({"npm": 1, "pypi": 2}, summary["purl_types"])
        self.assertEqual(["Jinja2@3.1.6"], summary["python_missing_license_metadata"])
        self.assertEqual("Go resolves no third-party modules", summary["go_boundary"])

    def test_missing_npm_license_fails_closed(self) -> None:
        report = payload(
            component("lzug", "0.1.0", "pkg:pypi/lzug@0.1.0", "AGPL-3.0-or-later"),
            component("rxjs", "7.8.2", "pkg:npm/rxjs@7.8.2"),
        )

        with self.assertRaisesRegex(ValueError, "npm components without license metadata"):
            validate_dependencies(report, "module example.invalid/lzug\n\ngo 1.26\n", set())

    def test_go_module_graph_uses_all_modules_resolved_by_go(self) -> None:
        graph = "\n".join(
            json.dumps(module)
            for module in (
                {"Path": "github.com/lxndrp/lzug/operator-cli", "Main": True},
                {"Path": "filippo.io/age", "Version": "v1.3.2"},
                {"Path": "c2sp.org/CCTV/age", "Version": "v0.0.0-test"},
            )
        )
        with patch(
            "scripts.sbom.subprocess.run",
            return_value=subprocess.CompletedProcess(["go"], 0, graph, ""),
        ) as run:
            main, modules = go_module_graph(
                "module github.com/lxndrp/lzug/operator-cli\n\ngo 1.26\n",
                go_sum=("filippo.io/age v1.3.2 h1:test\nc2sp.org/CCTV/age v0.0.0-test h1:test\n"),
            )

        self.assertEqual("github.com/lxndrp/lzug/operator-cli", main)
        self.assertEqual({"filippo.io/age", "c2sp.org/CCTV/age"}, modules)
        run.assert_called_once_with(
            ["go", "list", "-mod=readonly", "-m", "-json", "all"],
            cwd=Path("operator-cli").resolve(),
            check=True,
            capture_output=True,
            text=True,
        )

    def test_transitive_go_modules_from_the_resolved_graph_are_accepted(self) -> None:
        report = payload(
            component("lzug", "0.1.0", "pkg:pypi/lzug@0.1.0", "AGPL-3.0-or-later"),
            component("rxjs", "7.8.2", "pkg:npm/rxjs@7.8.2", "Apache-2.0"),
            component(
                "example.invalid/direct",
                "v1.0.0",
                "pkg:golang/example.invalid/direct@v1.0.0",
            ),
            component(
                "example.invalid/transitive",
                "v1.0.0",
                "pkg:golang/example.invalid/transitive@v1.0.0",
            ),
        )

        summary = validate_dependencies(
            report,
            "module example.invalid/lzug\n\ngo 1.26\n\nrequire example.invalid/direct v1.0.0\n",
            {"example.invalid/direct", "example.invalid/transitive"},
        )

        self.assertEqual("2 resolved third-party module components", summary["go_boundary"])

    def test_go_module_outside_the_resolved_graph_is_rejected(self) -> None:
        report = payload(
            component("lzug", "0.1.0", "pkg:pypi/lzug@0.1.0", "AGPL-3.0-or-later"),
            component("rxjs", "7.8.2", "pkg:npm/rxjs@7.8.2", "Apache-2.0"),
            component(
                "example.invalid/direct",
                "v1.0.0",
                "pkg:golang/example.invalid/direct@v1.0.0",
            ),
            component(
                "example.invalid/foreign",
                "v1.0.0",
                "pkg:golang/example.invalid/foreign@v1.0.0",
            ),
        )

        with self.assertRaisesRegex(ValueError, "undeclared Go modules: example.invalid/foreign"):
            validate_dependencies(
                report,
                "module example.invalid/lzug\n\ngo 1.26\n",
                {"example.invalid/direct"},
            )

    def test_declared_go_modules_must_be_present(self) -> None:
        report = payload(
            component("lzug", "0.1.0", "pkg:pypi/lzug@0.1.0", "AGPL-3.0-or-later"),
            component("rxjs", "7.8.2", "pkg:npm/rxjs@7.8.2", "Apache-2.0"),
        )

        with self.assertRaisesRegex(ValueError, "Declared Go modules missing"):
            validate_dependencies(
                report,
                "module example.invalid/lzug\n\ngo 1.26\n\nrequire example.invalid/lib v1.0.0\n",
                {"example.invalid/lib"},
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
            report, "module github.com/lxndrp/lzug/operator-cli\n\ngo 1.26\n", set()
        )

        self.assertEqual("Go resolves no third-party modules", summary["go_boundary"])

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

        summary = validate_cli(
            report, "module github.com/lxndrp/lzug/operator-cli\n\ngo 1.26\n", {}
        )

        self.assertEqual("lzug-admin-linux-amd64", summary["artifact"])
        self.assertEqual(2, summary["go_components"])

    def test_dependency_inventory_does_not_require_upstream_test_modules(self) -> None:
        report = payload(
            component("lzug", "0.1.0", "pkg:pypi/lzug@0.1.0", "AGPL-3.0-or-later"),
            component("rxjs", "7.8.2", "pkg:npm/rxjs@7.8.2", "Apache-2.0"),
            component(
                "example.invalid/runtime", "v1.0.0", "pkg:golang/example.invalid/runtime@v1.0.0"
            ),
        )
        validate_dependencies(
            report,
            "module example.invalid/lzug\nrequire example.invalid/runtime v1.0.0\n",
            {"example.invalid/runtime", "example.invalid/upstream-tests"},
        )

    def test_cli_inventory_is_bound_to_the_binary_and_rejects_missing_embedded_modules(
        self,
    ) -> None:
        go_mod = "module example.invalid/lzug\nrequire example.invalid/runtime v1.0.0\n"
        info = {
            "Main": {"Path": "example.invalid/lzug"},
            "Deps": [{"Path": "example.invalid/runtime", "Version": "v1.0.0"}],
        }
        with patch(
            "scripts.sbom.subprocess.run",
            return_value=subprocess.CompletedProcess(["go"], 0, json.dumps(info), ""),
        ):
            modules = cli_modules(Path("binary"), go_mod)
        self.assertEqual({"example.invalid/runtime": "v1.0.0"}, modules)
        report = payload(
            component("example.invalid/lzug", "UNKNOWN", "pkg:golang/example.invalid/lzug"),
            component("stdlib", "go1.26.5", "pkg:golang/stdlib@1.26.5"),
            source_name="lzug-admin-linux-amd64",
        )
        report["metadata"]["component"]["type"] = "file"
        with self.assertRaisesRegex(ValueError, "missing embedded Go modules"):
            validate_cli(report, go_mod, modules)
        report["components"].append(
            component(
                "example.invalid/runtime", "v1.0.0", "pkg:golang/example.invalid/runtime@v1.0.0"
            )
        )
        validate_cli(report, go_mod, modules)
        report["components"][-1]["version"] = "v9.9.9"
        with self.assertRaisesRegex(ValueError, "version differs"):
            validate_cli(report, go_mod, modules)
        report["components"][-1]["version"] = "v1.0.0"
        report["components"].append(
            component(
                "example.invalid/upstream-tests",
                "v1.0.0",
                "pkg:golang/example.invalid/upstream-tests@v1.0.0",
            )
        )
        with self.assertRaisesRegex(ValueError, "absent from the binary"):
            validate_cli(report, go_mod, modules)
        info["Main"]["Path"] = "example.invalid/foreign"
        with (
            patch(
                "scripts.sbom.subprocess.run",
                return_value=subprocess.CompletedProcess(["go"], 0, json.dumps(info), ""),
            ),
            self.assertRaisesRegex(ValueError, "main module"),
        ):
            cli_modules(Path("binary"), go_mod)

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

    def test_release_sbom_aggregates_eight_detailed_boms(self) -> None:
        details = release_detail_payloads()

        report = aggregate_release_sbom(
            details,
            "1.2.3",
            "v1.2.3",
            "a" * 40,
        )
        summary = validate_release(report)

        self.assertEqual({"golang": 2, "npm": 1, "pypi": 1}, summary["purl_types"])
        self.assertEqual(
            report,
            aggregate_release_sbom(details, "1.2.3", "v1.2.3", "a" * 40),
        )

    def test_release_sbom_fails_closed_for_incomplete_detailed_inventory(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires dependency, image, and six CLI SBOMs"):
            aggregate_release_sbom(
                release_detail_payloads()[:-1],
                "1.2.3",
                "v1.2.3",
                "a" * 40,
            )


def release_detail_payloads() -> list[dict]:
    dependency = payload(
        component("lzug", "1.2.3", "pkg:pypi/lzug@1.2.3", "AGPL-3.0-or-later"),
        component("rxjs", "7.8.2", "pkg:npm/rxjs@7.8.2", "Apache-2.0"),
    )
    image = payload(
        component("lzug", "1.2.3", "pkg:pypi/lzug@1.2.3", "AGPL-3.0-or-later"),
        source_name="ghcr.io/lxndrp/lzug:1.2.3",
    )
    cli_component = component(
        "github.com/lxndrp/lzug/operator-cli",
        "1.2.3",
        "pkg:golang/github.com/lxndrp/lzug/operator-cli@1.2.3",
    )
    stdlib = component("stdlib", "go1.26.5", "pkg:golang/stdlib@go1.26.5")
    cli_payloads = [
        payload(cli_component, stdlib, source_name=f"lzug-admin-{target}")
        for target in (
            "linux-amd64",
            "linux-arm64",
            "darwin-amd64",
            "darwin-arm64",
            "windows-amd64",
            "windows-arm64",
        )
    ]
    return [dependency, image, *cli_payloads]


if __name__ == "__main__":
    unittest.main()
