"""Architecture contracts for the backend responsibility packages."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from typing import get_type_hints

from backend.application.exam_lifecycle import ExamLifecycleApplication
from backend.application.exam_lifecycle_contracts import (
    DayCloseCommand,
    DayReopenCommand,
    RoundDecisionCommand,
    RoundReopenCommand,
)
from backend.execution.protocol_ports import ProtocolReferencesSnapshot
from backend.execution.slot_ports import DayMutationRequest

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "src" / "backend"
TEST_ROOT = Path(__file__).resolve().parent

CORE_PACKAGES = frozenset(
    {
        "application",
        "assessment",
        "calendar",
        "execution",
        "identity",
        "integrations",
        "notifications",
        "operations",
        "persistence",
        "presentation",
        "planning",
    }
)

# These modules are deliberate outer adapters or shared runtime contracts.
# HTTP/API relocation belongs to #646; the executable module paths are stable
# container and operator-CLI contracts.
ROOT_MODULE_OWNERS = {
    "__init__.py": "package-bootstrap",
    "admin_socket.py": "operations-adapter",
    "admin_socket_artifacts.py": "operations-adapter",
    "admin_socket_path.py": "operations-adapter",
    "admin_socket_protocol.py": "operations-adapter",
    "api_contracts.py": "api",
    "composition.py": "composition-root",
    "e2e_server.py": "api-bootstrap",
    "errors.py": "shared-contracts",
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
    "planning_ports.py": "planning-owned-contracts",
    "public_lifecycle.py": "runtime-contract",
    "runtime_policy.py": "runtime-foundation",
    "runtime.py": "runtime-foundation",
    "security.py": "runtime-foundation",
    "server.py": "api-bootstrap",
    "settings.py": "runtime-foundation",
    "synthetic_fixtures.py": "fixture-runtime",
    "version.py": "runtime-contract",
}

ALLOWED_PACKAGE_DEPENDENCIES = {
    "application": frozenset(
        {
            "assessment",
            "calendar",
            "execution",
            "identity",
            "integrations",
            "operations",
            "persistence",
            "planning",
            "notifications",
        }
    ),
    "assessment": frozenset(),
    "calendar": frozenset(),
    "execution": frozenset(
        {"calendar", "identity", "integrations", "notifications", "persistence", "presentation"}
    ),
    "identity": frozenset(),
    "integrations": frozenset({"identity", "notifications", "persistence"}),
    "notifications": frozenset(),
    "operations": frozenset({"identity", "integrations", "persistence"}),
    "persistence": frozenset({"calendar", "identity", "notifications"}),
    "presentation": frozenset(),
    "planning": frozenset({"calendar", "integrations", "notifications", "persistence"}),
}

TEST_OWNERS = {
    "api": frozenset(
        {
            "test_api.py",
            "test_e2e_server.py",
            "test_exam_venue_http.py",
            "test_fastapi_app.py",
            "test_fastapi_assembly.py",
            "test_fastapi_assembly_export.py",
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
            "runner.py",
            "test_synthetic_fixtures.py",
            "test_operator_cli_layout.py",
            "test_package_boundaries.py",
            "test_exam_export_renderers.py",
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
            "test_identity_ports.py",
            "test_local_auth.py",
        }
    ),
    "integrations": frozenset({"test_map_provider.py", "test_notification_delivery.py"}),
    "calendar": frozenset({"test_calendar.py", "test_calendar_ports.py"}),
    "notifications": frozenset({"test_notifications.py"}),
    "operations": frozenset(
        {
            "test_admin.py",
            "test_admin_socket.py",
            "test_admin_socket_artifacts.py",
            "test_artifact_limits.py",
            "test_backup_recipients.py",
            "test_backup_restore.py",
            "test_diagnostics.py",
            "test_healthcheck.py",
            "test_lifecycle.py",
        }
    ),
    "persistence": frozenset(
        {"test_database.py", "test_exam_venue_migration.py", "test_persistence.py"}
    ),
    "planning": frozenset(
        {
            "planning_support.py",
            "test_candidate_days.py",
            "test_exam_venues.py",
            "test_plan_consequences.py",
            "test_planning.py",
            "test_planning_venue_service.py",
            "test_planning_venue_policy.py",
            "test_planning_venue_ports.py",
            "test_planning_resource_adapter.py",
            "test_planning_resources.py",
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

        class RuntimeImports(ast.NodeVisitor):
            def __init__(self) -> None:
                self.nodes: list[ast.AST] = []

            def visit_If(self, node: ast.If) -> None:
                if isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
                    for item in node.orelse:
                        self.visit(item)
                    return
                self.generic_visit(node)

            def visit_Import(self, node: ast.Import) -> None:
                self.nodes.append(node)

            def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
                self.nodes.append(node)

        visitor = RuntimeImports()
        visitor.visit(tree)
        for node in visitor.nodes:
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
    def test_consequence_orchestration_uses_public_ports_not_models_or_adapters(self) -> None:
        modules = (
            "application/plan_consequences.py",
            "application/venue_consequences.py",
        )
        forbidden = {
            "backend.persistence.models",
            "backend.persistence.application_consequences",
            "backend.persistence.application_consequence_store",
            "backend.calendar.service",
            "backend.notifications.service",
        }
        for relative in modules:
            with self.subTest(module=relative):
                tree = ast.parse((BACKEND_ROOT / relative).read_text(encoding="utf-8"))
                imports = {
                    alias.name
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Import)
                    for alias in node.names
                }
                imports.update(
                    node.module
                    for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom) and node.module is not None
                )
                self.assertFalse(imports & forbidden)

    def test_exam_lifecycle_application_accepts_named_commands(self) -> None:
        expected = {
            "close_exam_day": DayCloseCommand,
            "reopen_exam_day": DayReopenCommand,
            "close_exam_round": RoundDecisionCommand,
            "cancel_exam_round": RoundDecisionCommand,
            "reopen_exam_round": RoundReopenCommand,
        }
        for method_name, command_type in expected.items():
            with self.subTest(method=method_name):
                method = getattr(ExamLifecycleApplication, method_name)
                self.assertIs(get_type_hints(method)["command"], command_type)

    def test_execution_does_not_import_assessment_orm_models(self) -> None:
        assessment_models = {
            "AssessmentModelVersion",
            "CommitteeAssessment",
            "ExamResult",
            "ExamRoundAssessmentBinding",
            "ExternalExamResult",
            "IndividualAssessment",
            "ResultCalculation",
            "ResultCommunication",
            "ResultCorrection",
            "ResultDetermination",
            "ResultRecordConfirmation",
            "ResultRetention",
        }
        for path in sorted((BACKEND_ROOT / "execution").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module == "backend.persistence.models"
                for alias in node.names
            }
            with self.subTest(module=path.relative_to(BACKEND_ROOT)):
                self.assertFalse(assessment_models & imported)

    def test_execution_lifecycle_does_not_import_planning_round_orm(self) -> None:
        foreign_models = {
            "CandidateCommitteeAssignment",
            "CandidateExamDay",
            "CalendarEvent",
            "CommitteeMember",
            "ConfirmedPlanRevision",
            "ExamHalfYear",
            "ExamRound",
            "MemberAvailability",
            "PlanConsequence",
            "PlanConsequenceBatch",
            "PlanningSettings",
            "RoundCandidate",
        }
        for relative in (
            "execution/exam_day_closures.py",
            "execution/exam_round_lifecycle.py",
        ):
            tree = ast.parse((BACKEND_ROOT / relative).read_text(encoding="utf-8"))
            imported = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module == "backend.persistence.models"
                for alias in node.names
            }
            with self.subTest(module=relative):
                self.assertFalse(foreign_models & imported)

    def test_application_transport_does_not_import_composition_root(self) -> None:
        for relative in ("application/__init__.py", "application/transport.py"):
            with self.subTest(module=relative):
                tree = ast.parse((BACKEND_ROOT / relative).read_text(encoding="utf-8"))
                imports = {
                    alias.name
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Import)
                    for alias in node.names
                }
                imports.update(
                    node.module
                    for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom) and node.module is not None
                )
                self.assertNotIn("backend.composition", imports)

    def test_notification_consumers_receive_composition_instead_of_importing_it(self) -> None:
        modules = (
            "execution/absence.py",
            "execution/exam_day_closures.py",
            "execution/exam_round_lifecycle.py",
            "planning/plan_consequences.py",
            "planning/venue_consequences.py",
            "planning/exam_venues.py",
            "application/exam_venue_api.py",
            "application/plan_consequences.py",
            "application/venue_consequences.py",
        )
        for relative in modules:
            with self.subTest(module=relative):
                tree = ast.parse((BACKEND_ROOT / relative).read_text(encoding="utf-8"))
                imports = {
                    alias.name
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Import)
                    for alias in node.names
                }
                imports.update(
                    node.module
                    for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom) and node.module is not None
                )
                self.assertNotIn("backend.composition", imports)

    def test_planning_consequence_policies_do_not_import_runtime_adapters(self) -> None:
        for relative in (
            "planning/plan_consequences.py",
            "planning/venue_consequences.py",
        ):
            tree = ast.parse((BACKEND_ROOT / relative).read_text(encoding="utf-8"))
            imports = {
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module is not None
            }
            with self.subTest(module=relative):
                self.assertFalse(
                    {
                        "backend.calendar",
                        "backend.notifications",
                        "backend.integrations",
                        "backend.persistence",
                    }
                    & imports
                )

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

    def test_assessment_core_has_no_persistence_http_or_renderer_dependencies(self) -> None:
        forbidden = (
            "backend.persistence",
            "backend.composition",
            "backend.presentation",
            "fastapi",
            "sqlalchemy",
        )
        for path in sorted((BACKEND_ROOT / "assessment").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module is not None:
                    imports.append(node.module)
            for module in imports:
                with self.subTest(path=path.name, module=module):
                    self.assertFalse(
                        any(
                            module == prefix or module.startswith(f"{prefix}.")
                            for prefix in forbidden
                        ),
                        f"Assessment imports outer adapter or transport module {module}",
                    )

    def test_core_package_dependency_graph_is_acyclic(self) -> None:
        graph = {package: _package_dependencies(package) for package in CORE_PACKAGES}
        remaining = set(graph)
        while remaining:
            leaves = {package for package in remaining if not (graph[package] & remaining)}
            self.assertTrue(leaves, f"cyclic backend package dependencies: {sorted(remaining)}")
            remaining -= leaves

    def test_notifications_policy_has_no_provider_or_persistence_dependencies(self) -> None:
        forbidden = {
            "backend.persistence",
            "backend.integrations",
            "sqlalchemy",
            "smtplib",
            "pywebpush",
        }
        for path in sorted((BACKEND_ROOT / "notifications").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            }
            imports.update(
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module is not None
            )
            self.assertFalse(
                forbidden & imports,
                f"{path.relative_to(BACKEND_ROOT)} imports provider or persistence details",
            )

    def test_execution_protocol_use_case_and_port_are_framework_and_orm_free(self) -> None:
        forbidden = {
            "backend.persistence",
            "backend.presentation",
            "backend.fastapi",
            "sqlalchemy",
            "fastapi",
        }
        for relative in (
            "execution/exam_protocols.py",
            "execution/protocol_ports.py",
        ):
            path = BACKEND_ROOT / relative
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            }
            imports.update(
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module is not None
            )
            self.assertFalse(
                forbidden & imports,
                f"{relative} imports transport, presentation, or persistence details",
            )

    def test_execution_day_guard_and_protocol_export_use_named_typed_contracts(self) -> None:
        self.assertNotIn("payload", DayMutationRequest.__annotations__)
        self.assertIn("expected_day_revision", DayMutationRequest.__annotations__)
        self.assertEqual(
            {
                "candidate",
                "round",
                "day",
                "slot",
                "candidate_attendance",
                "location",
                "participants",
                "assessment",
            },
            set(ProtocolReferencesSnapshot.__annotations__),
        )

    def test_committee_identity_use_case_has_no_transitive_transport_or_persistence_imports(
        self,
    ) -> None:
        pending = ["backend.identity.committee_admin"]
        visited: set[str] = set()
        while pending:
            module = pending.pop()
            if module in visited:
                continue
            visited.add(module)
            relative = module.removeprefix("backend.").replace(".", "/")
            path = BACKEND_ROOT / f"{relative}.py"
            if not path.exists():
                path = BACKEND_ROOT / relative / "__init__.py"
            if not path.exists():
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

            class RuntimeImports(ast.NodeVisitor):
                def __init__(self, current_module: str) -> None:
                    self.current_module = current_module
                    self.modules: set[str] = set()

                def visit_If(self, node: ast.If) -> None:
                    if isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
                        for item in node.orelse:
                            self.visit(item)
                        return
                    self.generic_visit(node)

                def visit_Import(self, node: ast.Import) -> None:
                    self.modules.update(alias.name for alias in node.names)

                def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
                    if node.level:
                        base = self.current_module.rsplit(".", node.level)[0]
                        imported = f"{base}.{node.module}" if node.module else base
                    else:
                        imported = node.module or ""
                    self.modules.add(imported)
                    for alias in node.names:
                        self.modules.add(f"{imported}.{alias.name}")

            imports = RuntimeImports(module)
            imports.visit(tree)
            for imported in imports.modules:
                if imported.startswith("backend."):
                    pending.append(imported)
        forbidden = sorted(
            module
            for module in visited
            if module.startswith("backend.persistence")
            or module.startswith("backend.fastapi")
            or module.startswith("backend.application.repositories")
        )
        self.assertEqual(forbidden, [])

    def test_every_backend_test_has_exactly_one_owner(self) -> None:
        assigned = [name for names in TEST_OWNERS.values() for name in names]
        self.assertEqual(len(assigned), len(set(assigned)), "a backend test has multiple owners")
        self.assertEqual(
            set(assigned),
            {path.name for path in TEST_ROOT.glob("*.py") if path.name != "__init__.py"},
        )


if __name__ == "__main__":
    unittest.main()
