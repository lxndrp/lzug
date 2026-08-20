"""Public-demo routes and the server-side default-deny mutation policy."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from zoneinfo import ZoneInfo

from backend.app import ForbiddenRequestError, LzugHandler
from backend.auth import AuthContext, AuthenticationError

from .artifacts import load_manifest, load_runtime_status

DEMO_ROLES = {
    "chair": {"account_id": 1, "person_id": 1, "display_name": "Testperson Alpha"},
    "examiner": {"account_id": 2, "person_id": 3, "display_name": "Testperson Gamma"},
}

COMMON_CAPABILITIES = frozenset({"availability:write-own", "attendance:write-own"})
CHAIR_CAPABILITIES = COMMON_CAPABILITIES | frozenset(
    {
        "round:write",
        "planning-settings:write",
        "candidate-days:generate",
        "availability:coordinate",
        "planning-proposal:generate",
        "planning-proposal:replace",
        "planning-proposal:confirm",
        "attendance:coordinate",
        "exam-status:write",
    }
)


class DemoRuntimePolicy:
    """Expose only the explicitly approved public-demo behavior."""

    def __init__(self, app_manifest_path: Path, seed_manifest_path: Path):
        self.app_manifest = load_manifest(app_manifest_path)
        self.seed_manifest = load_manifest(seed_manifest_path)
        self.runtime_status = load_runtime_status(seed_manifest_path.parent, self.seed_manifest)

    def handle_public_get(self, handler: LzugHandler, path_parts: list[str]) -> bool:
        if path_parts != ["demo", "status"]:
            return False
        next_reset = self._next_reset()
        handler.respond(
            {
                "mode": "demo",
                "product_version": self.app_manifest["product"]["version"],
                "product_commit": self.app_manifest["product"]["commit"],
                "runtime_contract": self.app_manifest["runtime_contract"],
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

    def handle_public_post(self, handler: LzugHandler, path_parts: list[str]) -> bool:
        if path_parts != ["demo", "session"]:
            return False
        if not handler.allow_public_auth_request(path_parts):
            return True
        payload = handler.read_json()
        role_name = payload.get("role")
        role = DEMO_ROLES.get(role_name) if isinstance(role_name, str) else None
        if role is None:
            handler.respond({"error": "Unknown demo role."}, HTTPStatus.BAD_REQUEST)
            return True
        try:
            credentials = handler.authentication_repository.create_session(
                role["account_id"], ttl=handler.session_ttl
            )
        except AuthenticationError:
            handler.respond({"error": "Demo role is unavailable."}, HTTPStatus.SERVICE_UNAVAILABLE)
            return True
        handler.issue_session_cookies(credentials)
        handler.respond(
            {
                "authenticated": True,
                "role": role_name,
                "display_name": role["display_name"],
                "expires_at": credentials.expires_at,
            },
            HTTPStatus.CREATED,
        )
        return True

    def allow_product_auth(self) -> bool:
        return False

    def session_view(self, context: AuthContext) -> dict:
        role_name = self._role_name(context)
        role = DEMO_ROLES[role_name]
        capabilities = CHAIR_CAPABILITIES if role_name == "chair" else COMMON_CAPABILITIES
        return {
            "demo_role": role_name,
            "display_name": role["display_name"],
            "capabilities": sorted(capabilities),
        }

    def authorize_mutation(
        self,
        handler: LzugHandler,
        method: str,
        path_parts: list[str],
        context: AuthContext,
    ) -> None:
        role = self._role_name(context)
        path = "/".join(path_parts)
        if method == "POST" and path in {"session/rotate", "session/logout"}:
            return
        if method == "DELETE":
            raise ForbiddenRequestError("This write operation is disabled in the demo.")

        if role == "examiner":
            examiner_allowed = method == "POST" and path == "member-availabilities"
            examiner_allowed = examiner_allowed or (
                method == "PATCH"
                and len(path_parts) == 2
                and path_parts[0] == "member-availabilities"
            )
            examiner_allowed = examiner_allowed or (
                method == "PATCH"
                and len(path_parts) == 5
                and path_parts[0] == "confirmed-plan-days"
                and path_parts[2] == "assignments"
                and path_parts[4] == "attendance"
            )
            if examiner_allowed:
                return
            raise ForbiddenRequestError("This write operation is disabled for this demo role.")

        if self._chair_mutation_allowed(method, path_parts):
            return
        raise ForbiddenRequestError("This write operation is disabled in the demo.")

    @staticmethod
    def _chair_mutation_allowed(method: str, path_parts: list[str]) -> bool:
        path = "/".join(path_parts)
        if method == "POST":
            if path in {
                "planning-proposals",
                "candidate-exam-days/generate",
                "planning-settings",
                "member-availabilities",
            }:
                return True
            return (
                len(path_parts) == 3
                and path_parts[0] == "exam-rounds"
                and path_parts[2] in {"request-availabilities", "confirm-plan"}
            ) or (
                len(path_parts) == 5
                and path_parts[0] == "confirmed-plan-days"
                and path_parts[2] == "slots"
                and path_parts[4] == "start"
            )
        if method == "PUT":
            return (
                len(path_parts) == 3
                and path_parts[0] == "exam-rounds"
                and path_parts[2] == "planning-proposal"
            )
        if method == "PATCH":
            if len(path_parts) == 2 and path_parts[0] in {
                "exam-rounds",
                "planning-settings",
                "member-availabilities",
            }:
                return True
            return (
                len(path_parts) == 5
                and path_parts[0] == "confirmed-plan-days"
                and path_parts[2] in {"slots", "assignments"}
                and path_parts[4] in {"attendance", "status"}
            )
        return False

    @staticmethod
    def _role_name(context: AuthContext) -> str:
        for name, role in DEMO_ROLES.items():
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
