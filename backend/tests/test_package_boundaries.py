"""Architecture contracts for the backend responsibility packages."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "src" / "backend"
TEST_ROOT = Path(__file__).resolve().parent

CORE_PACKAGES = frozenset(
    {
        "application",
        "assessment",
        "execution",
        "identity",
        "integrations",
        "operations",
        "persistence",
        "planning",
    }
)

# These modules are deliberate outer adapters or shared runtime contracts.
# HTTP/API relocation belongs to #646; the executable module paths are stable
# container and operator-CLI contracts.
ROOT_MODULE_OWNERS = {
    "__init__.py": "package-bootstrap",
    "admin.py": "operations-adapter",
    "admin_socket.py": "operations-adapter",
    "admin_socket_artifacts.py": "operations-adapter",
    "admin_socket_path.py": "operations-adapter",
    "admin_socket_protocol.py": "operations-adapter",
    "api_contracts.py": "api",
    "artifact_stream.py": "operations-adapter",
    "build_metadata.py": "runtime-contract",
    "e2e_server.py": "api-bootstrap",
    "fastapi_app.py": "api",
    "fastapi_assembly.py": "api",
    "fastapi_assessment.py": "api",
    "fastapi_dependencies.py": "api",
    "fastapi_execution.py": "api",
    "fastapi_http.py": "api",
    "fastapi_integration_routes.py": "api",
    "fastapi_master_data.py": "api",
    "fastapi_operations_routes.py": "api",
    "fastapi_planning_router.py": "api",
    "fastapi_runtime.py": "api",
    "healthcheck.py": "operations-adapter",
    "observability.py": "runtime-foundation",
    "public_lifecycle.py": "runtime-contract",
    "runtime_policy.py": "runtime-foundation",
    "runtime.py": "runtime-foundation",
    "security.py": "runtime-foundation",
    "server.py": "api-bootstrap",
    "settings.py": "runtime-foundation",
    "version.py": "runtime-contract",
}

ALLOWED_PACKAGE_DEPENDENCIES = {
    "application": frozenset(
        {
            "assessment",
            "execution",
            "identity",
            "integrations",
            "operations",
            "persistence",
            "planning",
        }
    ),
    "assessment": frozenset({"execution", "identity", "persistence"}),
    "execution": frozenset({"identity", "integrations", "persistence"}),
    "identity": frozenset({"persistence"}),
    "integrations": frozenset({"identity", "persistence"}),
    "operations": frozenset({"identity", "integrations", "persistence"}),
    "persistence": frozenset(),
    "planning": frozenset({"integrations", "persistence"}),
}

TEST_OWNERS = {
    "api": frozenset(
        {
            "test_api.py",
            "test_e2e_server.py",
            "test_exam_venue_http.py",
            "test_fastapi_app.py",
            "test_fastapi_assembly.py",
            "test_fastapi_dependencies.py",
            "test_fastapi_execution_routing.py",
            "test_fastapi_integration_routes.py",
            "test_fastapi_master_data.py",
            "test_fastapi_operations_routes.py",
            "test_fastapi_planning_router.py",
            "test_fastapi_request_stream.py",
            "test_http_contract_parity.py",
            "test_openapi_contract.py",
        }
    ),
    "application": frozenset(
        {
            "test_exam_venue_api.py",
            "test_admin_application.py",
            "test_person_memberships.py",
            "test_repository.py",
            "test_resource_access.py",
            "test_planning_payloads.py",
            "test_contract_validation.py",
            "test_venue_transport.py",
        }
    ),
    "assessment": frozenset({"test_exam_results.py"}),
    "crosscutting": frozenset(
        {
            "fixture_data.py",
            "helpers.py",
            "test_operator_cli_layout.py",
            "test_package_boundaries.py",
        }
    ),
    "execution": frozenset(
        {
            "test_absence.py",
            "test_exam_day_closures.py",
            "test_exam_protocols.py",
            "test_exam_round_lifecycle.py",
        }
    ),
    "identity": frozenset(
        {
            "test_auth.py",
            "test_authorization.py",
            "test_committee_admin.py",
            "test_local_auth.py",
        }
    ),
    "integrations": frozenset(
        {"test_calendar.py", "test_map_provider.py", "test_notifications.py"}
    ),
    "operations": frozenset(
        {
            "test_admin.py",
            "test_admin_socket.py",
            "test_admin_socket_artifacts.py",
            "test_artifact_limits.py",
            "test_backup_recipients.py",
            "test_backup_restore.py",
            "test_diagnostics.py",
            "test_lifecycle.py",
        }
    ),
    "persistence": frozenset(
        {"test_database.py", "test_exam_venue_migration.py", "test_persistence.py"}
    ),
    "planning": frozenset(
        {
            "test_candidate_days.py",
            "test_exam_venues.py",
            "test_plan_consequences.py",
            "test_planning.py",
            "test_venue_consequences.py",
        }
    ),
    "runtime": frozenset(
        {
            "test_security.py",
            "test_settings.py",
            "test_version.py",
            "test_runtime.py",
            "test_runtime_adapters.py",
            "test_public_lifecycle.py",
        }
    ),
}


def _package_dependencies(package: str) -> set[str]:
    dependencies: set[str] = set()
    for path in (BACKEND_ROOT / package).glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            for name in names:
                parts = name.split(".")
                if len(parts) >= 2 and parts[0] == "backend" and parts[1] in CORE_PACKAGES:
                    dependencies.add(parts[1])
    dependencies.discard(package)
    return dependencies


class BackendPackageBoundaryTests(unittest.TestCase):
    def test_every_backend_module_has_one_responsibility_area(self) -> None:
        self.assertEqual(
            {
                path.name
                for path in BACKEND_ROOT.iterdir()
                if path.is_dir() and path.name != "__pycache__"
            },
            CORE_PACKAGES,
        )
        self.assertEqual(
            {path.name for path in BACKEND_ROOT.glob("*.py")},
            set(ROOT_MODULE_OWNERS),
        )

    def test_core_packages_follow_allowed_dependency_directions(self) -> None:
        actual = {package: _package_dependencies(package) for package in CORE_PACKAGES}
        unexpected = {
            package: dependencies - ALLOWED_PACKAGE_DEPENDENCIES[package]
            for package, dependencies in actual.items()
            if dependencies - ALLOWED_PACKAGE_DEPENDENCIES[package]
        }
        self.assertEqual(unexpected, {})

    def test_core_package_dependency_graph_is_acyclic(self) -> None:
        graph = {package: _package_dependencies(package) for package in CORE_PACKAGES}
        remaining = set(graph)
        while remaining:
            leaves = {package for package in remaining if not (graph[package] & remaining)}
            self.assertTrue(leaves, f"cyclic backend package dependencies: {sorted(remaining)}")
            remaining -= leaves

    def test_every_backend_test_has_exactly_one_owner(self) -> None:
        assigned = [name for names in TEST_OWNERS.values() for name in names]
        self.assertEqual(len(assigned), len(set(assigned)), "a backend test has multiple owners")
        self.assertEqual(
            set(assigned),
            {path.name for path in TEST_ROOT.glob("*.py") if path.name != "__init__.py"},
        )


if __name__ == "__main__":
    unittest.main()
