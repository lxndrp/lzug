"""Public-demo routes and the server-side default-deny mutation policy."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select

from backend.application import ForbiddenRequestError
from backend.auth import AuthContext, AuthenticationError
from backend.database import session_scope
from backend.models import AbsenceReport, ConfirmedPlanRevision, ExamDay, ReplacementResponse
from backend.settings import RuntimeSettings
from backend.transport import RequestContext

from .artifacts import load_runtime_manifests, load_runtime_status
from .scenarios import (
    expected_plan_change,
    scenario_overview,
)
from .workspaces import DemoWorkspace, DemoWorkspaceCapacityError, DemoWorkspaceManager

ROLE_NAMES = frozenset({"chair", "examiner", "replacement"})


@dataclass(frozen=True)
class DemoPathContract:
    """One testable link between UI, capability, HTTP boundary, and domain guard."""

    name: str
    roles: frozenset[str]
    scenario: str
    seed_state: str
    ui_action: str
    capability: str
    method: str
    path_pattern: str
    domain_authorization: str
    visible: bool
    allowed: bool

    def matches(self, method: str, path_parts: list[str]) -> bool:
        if method != self.method:
            return False
        expected_parts = self.path_pattern.strip("/").split("/")
        if len(expected_parts) != len(path_parts):
            return False
        return all(
            (
                actual.isdigit()
                if expected.startswith("{") and expected.endswith("}")
                else actual == expected
            )
            for expected, actual in zip(expected_parts, path_parts, strict=True)
        )


DEMO_READ_MATRIX = (
    DemoPathContract(
        "notifications-read-own",
        ROLE_NAMES,
        "Persönliche Hinweise",
        "isolated-own-notifications",
        "Eigene Benachrichtigungen lesen",
        "notifications:read-own",
        "GET",
        "/notifications",
        "NotificationService.list_own",
        True,
        True,
    ),
    DemoPathContract(
        "calendar-read-own",
        ROLE_NAMES,
        "Persönlicher Kalender",
        "isolated-own-calendar-events",
        "Eigene Kalenderereignisse lesen und einzeln laden",
        "calendar:read-own",
        "GET",
        "/calendar/events",
        "CalendarService.list_events",
        True,
        True,
    ),
)

DEMO_MUTATION_MATRIX = (
    DemoPathContract(
        "absence-report-own",
        frozenset({"examiner"}),
        "Dringlicher Ausfall und Ersatz",
        "confirmed-urgent-own-assignment",
        "Eigenen Ausfall melden",
        "absence:write-own",
        "POST",
        "/absence-reports",
        "AbsenceService.report",
        True,
        True,
    ),
    DemoPathContract(
        "absence-response-own",
        frozenset({"replacement"}),
        "Dringlicher Ausfall und Ersatz",
        "own-pending-replacement-request",
        "Eigene Anfrage mit verfügbar beantworten",
        "absence:respond-own",
        "PATCH",
        "/replacement-responses/{id}",
        "AbsenceService.respond",
        True,
        True,
    ),
    DemoPathContract(
        "absence-coordinate",
        frozenset({"chair"}),
        "Dringlicher Ausfall und Ersatz",
        "requested-available-replacement",
        "Vorgegebenen Ersatz auswählen",
        "absence:coordinate",
        "POST",
        "/absence-reports/{id}/select-replacement",
        "AbsenceService.select_replacement",
        True,
        True,
    ),
    DemoPathContract(
        "confirmed-plan-revise",
        frozenset({"chair"}),
        "Bestätigte Planänderung",
        "prepared-single-revision",
        "Vorbereitete Ortsänderung und Personentausch bestätigen",
        "confirmed-plan:revise",
        "PUT",
        "/exam-rounds/{id}/confirmed-plan",
        "PlanningService.save_confirmed_plan",
        True,
        True,
    ),
)

ROLE_CAPABILITIES = {
    "chair": frozenset(
        {
            "absence:coordinate",
            "confirmed-plan:revise",
            "notifications:read-own",
            "calendar:read-own",
        }
    ),
    "examiner": frozenset({"absence:write-own", "notifications:read-own", "calendar:read-own"}),
    "replacement": frozenset(
        {"absence:respond-own", "notifications:read-own", "calendar:read-own"}
    ),
}


class DemoRuntimePolicy:
    """Expose only the explicitly approved public-demo behavior."""

    def __init__(
        self,
        app_manifest_path: Path,
        seed_manifest_path: Path,
        *,
        workspace_dir: Path | None = None,
        capacity: int | None = None,
        settings: RuntimeSettings | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.app_manifest, self.seed_manifest = load_runtime_manifests(
            app_manifest_path, seed_manifest_path
        )
        profile = self.seed_manifest["fixture_profile"]
        self.demo_roles = {name: profile["roles"][name] for name in ROLE_NAMES}
        self.runtime_profile = profile
        self.demo_matrix_version = self.seed_manifest["fixture_catalog"]["demo_matrix_version"]
        self.runtime_status = load_runtime_status(seed_manifest_path.parent, self.seed_manifest)
        self.clock = clock
        configured = settings or RuntimeSettings.from_environment()
        configured_capacity = (
            capacity if capacity is not None else configured.demo.workspace_capacity
        )
        self.workspaces = DemoWorkspaceManager(
            workspace_dir or configured.demo.workspace_dir,
            ttl=timedelta(minutes=60),
            capacity=configured_capacity,
            clock=clock,
        )
        self.base_db_path: Path | None = None

    def handle_public_get(self, handler: RequestContext, path_parts: list[str]) -> bool:
        if path_parts == ["demo", "status"]:
            next_reset = self._next_reset()
            handler.respond(
                {
                    "mode": "demo",
                    "product_version": self.app_manifest["product"]["version"],
                    "product_commit": self.app_manifest["product"]["commit"],
                    "runtime_contract": self.app_manifest["runtime_contract"],
                    "demo_matrix_version": self.demo_matrix_version,
                    "fixture_catalog_version": self.seed_manifest["fixture_catalog"]["version"],
                    "fixture_catalog_revision": self.seed_manifest["fixture_catalog"]["revision"],
                    "seed_revision": self.seed_manifest["seed_revision"],
                    "schema_fingerprint": self.seed_manifest["schema"]["fingerprint"],
                    "initialized": self.runtime_status["initialized"],
                    "initialization_status": self.runtime_status["initialization_status"],
                    "initialized_at": self.runtime_status["initialized_at"],
                    "last_reset_at": self.runtime_status["last_reset_at"],
                    "reset_status": "scheduled",
                    "next_reset_at": next_reset.isoformat(),
                    "reset_timezone": "Europe/Berlin",
                    "notices": [
                        "Alle Eingaben sind flüchtig und werden beim Reset verworfen.",
                        "Keine realen personenbezogenen Daten eingeben.",
                        "Laufende Sitzungen enden beim Reset.",
                    ],
                }
            )
            return True
        if path_parts == ["demo", "scenarios"]:
            context = handler.require_authenticated()
            workspace = self._workspace(handler.session_token)
            role = self._role_name(context)
            handler.respond(
                scenario_overview(
                    handler.db_path,
                    role=role,
                    created_at=workspace.created_at,
                    expires_at=workspace.expires_at,
                    now=self.clock(),
                    runtime_profile=self.runtime_profile,
                )
            )
            return True
        return False

    def handle_public_post(self, handler: RequestContext, path_parts: list[str]) -> bool:
        if path_parts == ["demo", "session"]:
            self._start_or_switch_session(handler)
            return True
        if path_parts == ["demo", "reset"]:
            self._reset(handler)
            return True
        return False

    def allow_product_auth(self) -> bool:
        return False

    def database_for_request(self, base_db_path: Path, session_token: str | None) -> Path:
        self.base_db_path = base_db_path
        workspace = self.workspaces.resolve(base_db_path, session_token)
        return workspace.path if workspace is not None else base_db_path

    def external_notifications_enabled(self) -> bool:
        return False

    def session_view(self, handler: RequestContext, context: AuthContext) -> dict:
        role_name = self._role_name(context)
        role = self.demo_roles[role_name]
        workspace = self._workspace(handler.session_token)
        return {
            "demo_role": role_name,
            "display_name": role["display_name"],
            "capabilities": sorted(ROLE_CAPABILITIES[role_name]),
            "demo_matrix_version": self.demo_matrix_version,
            "demo_workspace_expires_at": workspace.expires_at.isoformat(),
        }

    def discard_session(self, handler: RequestContext, session_token: str | None) -> None:
        del handler
        self.workspaces.discard(session_token)

    def authorize_mutation(
        self,
        handler: RequestContext,
        method: str,
        path_parts: list[str],
        context: AuthContext,
    ) -> None:
        role = self._role_name(context)
        path = "/".join(path_parts)
        if method == "POST" and path == "session/logout":
            return
        payload = handler.read_json()
        if self._allows_absence_report(handler, role, method, path_parts, payload):
            return
        if self._allows_response(handler, role, method, path_parts, payload):
            return
        if self._allows_selection(handler, role, method, path_parts, payload):
            return
        if self._allows_plan_change(handler, role, method, path_parts, payload):
            return
        message = (
            "This write operation is disabled for this demo role."
            if role == "examiner"
            else "This write operation is disabled in the demo."
        )
        raise ForbiddenRequestError(message)

    def _start_or_switch_session(self, handler: RequestContext) -> None:
        if not handler.allow_public_auth_request(["demo", "session"]):
            return
        payload = handler.read_json()
        role_name = payload.get("role")
        role = self.demo_roles.get(role_name) if isinstance(role_name, str) else None
        if role is None or set(payload) != {"role"}:
            handler.respond({"error": "Unknown demo role."}, HTTPStatus.BAD_REQUEST)
            return
        base_db_path = self._base_path()
        previous_token = handler.session_token
        workspace = self.workspaces.resolve(base_db_path, previous_token)
        workspace_created = workspace is None
        if workspace is None:
            try:
                workspace = self.workspaces.create(base_db_path)
            except DemoWorkspaceCapacityError:
                handler.respond(
                    {"error": "Die Demo ist derzeit ausgelastet. Bitte später erneut versuchen."},
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )
                return
        else:
            handler.require_authenticated(require_actor=False, require_csrf=True)
            handler.authentication_repository.revoke_session(previous_token, reason="role-switch")
        handler.db_path = workspace.path
        remaining = self.workspaces.remaining(workspace)
        try:
            credentials = handler.authentication_repository.create_session(
                role["account_id"], now=self.clock(), ttl=remaining
            )
        except AuthenticationError:
            if workspace_created:
                self.workspaces.discard_workspace(workspace)
            else:
                self.workspaces.discard(previous_token)
            handler.respond({"error": "Demo role is unavailable."}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        self.workspaces.bind(workspace, credentials.token, previous_token=previous_token)
        handler.issue_session_cookies(
            credentials,
            max_age=max(1, int(remaining.total_seconds())),
        )
        handler.respond(
            {
                "authenticated": True,
                "role": role_name,
                "display_name": role["display_name"],
                "expires_at": credentials.expires_at,
            },
            HTTPStatus.CREATED,
        )

    def _reset(self, handler: RequestContext) -> None:
        context = handler.require_authenticated(require_csrf=True)
        role_name = self._role_name(context)
        previous_token = handler.session_token
        workspace = self._workspace(previous_token)
        self.workspaces.reset(self._base_path(), workspace)
        handler.db_path = workspace.path
        remaining = self.workspaces.remaining(workspace)
        credentials = handler.authentication_repository.create_session(
            self.demo_roles[role_name]["account_id"], now=self.clock(), ttl=remaining
        )
        self.workspaces.bind(workspace, credentials.token, previous_token=previous_token)
        handler.issue_session_cookies(
            credentials,
            max_age=max(1, int(remaining.total_seconds())),
        )
        handler.respond(
            {
                "status": "reset",
                "role": role_name,
                "expires_at": credentials.expires_at,
            }
        )

    def _allows_absence_report(self, handler, role, method, parts, payload) -> bool:
        if role != "examiner" or method != "POST" or parts != ["absence-reports"]:
            return False
        if set(payload) != {"exam_day_id", "exam_day_assignment_id", "day_revision"}:
            return False
        return (
            payload["exam_day_id"] == self.runtime_profile["absence"]["day_id"]
            and payload["exam_day_assignment_id"]
            == self.runtime_profile["absence"]["assignment_id"]
            and self._day_revision(handler.db_path, self.runtime_profile["absence"]["day_id"])
            == payload["day_revision"]
            and not self._absence_exists(handler.db_path)
        )

    def _allows_response(self, handler, role, method, parts, payload) -> bool:
        if (
            role != "replacement"
            or method != "PATCH"
            or len(parts) != 2
            or parts[0] != "replacement-responses"
            or not parts[1].isdigit()
            or payload != {"response": "available"}
        ):
            return False
        with session_scope(handler.db_path) as session:
            response = session.get(ReplacementResponse, int(parts[1]))
            return bool(
                response
                and response.committee_member_id
                == self.runtime_profile["roles"]["replacement"]["committee_member_id"]
                and response.response == "pending"
            )

    def _allows_selection(self, handler, role, method, parts, payload) -> bool:
        if (
            role != "chair"
            or method != "POST"
            or len(parts) != 3
            or parts[0] != "absence-reports"
            or parts[2] != "select-replacement"
            or not parts[1].isdigit()
            or set(payload) != {"committee_member_id", "version"}
            or payload["committee_member_id"]
            != self.runtime_profile["roles"]["replacement"]["committee_member_id"]
        ):
            return False
        with session_scope(handler.db_path) as session:
            report = session.get(AbsenceReport, int(parts[1]))
            response = (
                session.scalar(
                    select(ReplacementResponse).where(
                        ReplacementResponse.absence_report_id == report.id,
                        ReplacementResponse.committee_member_id
                        == self.runtime_profile["roles"]["replacement"]["committee_member_id"],
                    )
                )
                if report is not None
                else None
            )
            return bool(
                report
                and report.exam_day_id == self.runtime_profile["absence"]["day_id"]
                and report.version == payload["version"]
                and report.status == "replacement_requested"
                and response
                and response.response == "available"
            )

    def _allows_plan_change(self, handler, role, method, parts, payload) -> bool:
        if (
            role != "chair"
            or method != "PUT"
            or parts != ["exam-rounds", str(self.runtime_profile["round_id"]), "confirmed-plan"]
        ):
            return False
        expected = expected_plan_change(handler.db_path, self.runtime_profile)
        actual_revision = payload.get("revision")
        expected_revision = expected["revision"]
        payload_without_revision = {
            key: value for key, value in payload.items() if key != "revision"
        }
        expected_without_revision = {
            key: value for key, value in expected.items() if key != "revision"
        }
        if payload_without_revision != expected_without_revision:
            return False
        if not self._plan_change_exists(handler.db_path):
            return actual_revision == expected_revision
        return isinstance(actual_revision, int) and actual_revision < expected_revision

    @staticmethod
    def _day_revision(db_path: Path, day_id: int) -> int | None:
        with session_scope(db_path) as session:
            day = session.get(ExamDay, day_id)
            return day.revision if day is not None else None

    def _absence_exists(self, db_path: Path) -> bool:
        with session_scope(db_path) as session:
            return (
                session.scalar(
                    select(AbsenceReport.id).where(
                        AbsenceReport.exam_day_id == self.runtime_profile["absence"]["day_id"]
                    )
                )
                is not None
            )

    def _plan_change_exists(self, db_path: Path) -> bool:
        with session_scope(db_path) as session:
            return (
                session.scalar(
                    select(ConfirmedPlanRevision.id).where(
                        ConfirmedPlanRevision.exam_round_id == self.runtime_profile["round_id"]
                    )
                )
                is not None
            )

    def _workspace(self, token: str | None) -> DemoWorkspace:
        workspace = self.workspaces.resolve(self._base_path(), token)
        if workspace is None:
            raise ForbiddenRequestError("Demo workspace is unavailable or expired.")
        return workspace

    def _base_path(self) -> Path:
        if self.base_db_path is None:
            raise RuntimeError("Demo database boundary is not initialized")
        return self.base_db_path

    def _role_name(self, context: AuthContext) -> str:
        for name, role in self.demo_roles.items():
            if context.person_id == role["person_id"] and context.account_id == role["account_id"]:
                return name
        raise ForbiddenRequestError("This account is not available in the demo.")

    @staticmethod
    def _next_reset() -> datetime:
        timezone = ZoneInfo("Europe/Berlin")
        now = datetime.now(UTC).astimezone(timezone)
        candidate = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate
