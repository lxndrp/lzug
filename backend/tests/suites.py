"""Explicit backend test tiers, classified by the strongest exercised boundary.

Mixed modules belong to their strongest tier until their tests are split. This
keeps the quick unit entry point honest without hiding broader contracts.
"""

from __future__ import annotations

TEST_MODULES_BY_TIER: dict[str, frozenset[str]] = {
    "unit": frozenset(
        {
            "test_calendar_ports",
            "test_contract_validation",
            "test_exam_export_renderers",
            "test_healthcheck",
            "test_notification_delivery",
            "test_operator_cli_layout",
            "test_package_boundaries",
            "test_planning_payloads",
            "test_planning_resources",
            "test_planning_venue_policy",
            "test_settings",
            "test_synthetic_fixtures",
            "test_tiers",
            "test_version",
        }
    ),
    "component": frozenset(
        {
            "test_admin_application",
            "test_artifact_limits",
            "test_backup_recipients",
            "test_backup_restore",
            "test_candidate_days",
            "test_committee_admin",
            "test_database",
            "test_diagnostics",
            "test_exam_venue_api",
            "test_exam_venue_migration",
            "test_exam_venues",
            "test_fastapi_assembly",
            "test_fastapi_assembly_export",
            "test_fastapi_integration_routes",
            "test_fastapi_master_data",
            "test_fastapi_operations_routes",
            "test_http_contract_parity",
            "test_identity_ports",
            "test_local_auth",
            "test_persistence",
            "test_person_memberships",
            "test_planning",
            "test_planning_resource_adapter",
            "test_planning_venue_ports",
            "test_repository",
            "test_resource_access",
            "test_venue_transport",
        }
    ),
    "http": frozenset(
        {
            "test_absence",
            "test_api",
            "test_auth",
            "test_authorization",
            "test_calendar",
            "test_e2e_server",
            "test_exam_day_closures",
            "test_exam_protocols",
            "test_exam_results",
            "test_exam_round_lifecycle",
            "test_exam_venue_http",
            "test_fastapi_app",
            "test_fastapi_dependencies",
            "test_fastapi_execution_routing",
            "test_fastapi_planning_router",
            "test_fastapi_request_stream",
            "test_lifecycle",
            "test_map_provider",
            "test_notifications",
            "test_openapi_contract",
            "test_plan_consequences",
            "test_public_lifecycle",
            "test_runtime_adapters",
            "test_security",
            "test_venue_consequences",
        }
    ),
    "process": frozenset(
        {
            "test_admin",
            "test_admin_socket",
            "test_admin_socket_artifacts",
            "test_planning_venue_service",
            "test_runtime",
        }
    ),
}

TEST_TIERS = frozenset(TEST_MODULES_BY_TIER)
