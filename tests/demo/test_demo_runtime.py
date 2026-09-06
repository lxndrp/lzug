from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import UTC, datetime, time, timedelta
from http import HTTPStatus
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.database import session_scope
from backend.models import (
    CalendarEvent,
    ConfirmedPlanRevision,
    ExamDay,
    ExamSlot,
    Notification,
    NotificationDelivery,
    UserAccount,
)
from backend.security import RequestRateLimiter
from backend.tests.fixture_data import (
    ABSENCE_ASSIGNMENT_ID,
    ABSENCE_ASSIGNMENT_START_ID,
    ABSENCE_DAY_ID,
    DEMO_MATRIX_VERSION,
    DEMO_ROLES,
    FIXTURE_CATALOG_REVISION,
    FIXTURE_CATALOG_VERSION,
    PLAN_CHANGE_ASSIGNMENT_ID,
    PLAN_CHANGE_ASSIGNMENT_START_ID,
    PLAN_CHANGE_DAY_ID,
    PLAN_REPLACEMENT_MEMBER_ID,
    PUBLIC_DEMO_RUNTIME,
    REPLACEMENT_MEMBER_ID,
    ROUND_ID,
    TARGET_LOCATION_ID,
    TIME_ZONE,
    _closest_relative_exam_date,
    public_demo_seed_sql,
    seed_demo_scenarios,
)
from backend.tests.helpers import ApiServer, TempDatabase, TestLzugHandler
from demo.artifacts import (
    DemoArtifactError,
    build_app_manifest,
    build_seed,
    initialize_workdir,
)
from demo.contract import RUNTIME_CONTRACT, canonical_digest, demo_identity
from demo.runtime_policy import (
    DEMO_MUTATION_MATRIX,
    DEMO_READ_MATRIX,
    ROLE_CAPABILITIES,
    DemoRuntimePolicy,
)


class MutableClock:
    def __init__(self, value: datetime):
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, delta: timedelta) -> None:
        self.value += delta


class DemoTestHandler(TestLzugHandler):
    cookie_secure = False
    https_only = False
    session_ttl = timedelta(minutes=60)


class DemoRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.app_manifest = self.root / "app.json"
        self.seed_manifest = self.root / "seed.json"
        self.clock = MutableClock(datetime.now(UTC).replace(microsecond=0))
        self.seed_revision = self._write_manifests()
        DemoTestHandler.auth_rate_limiter = RequestRateLimiter(20, timedelta(minutes=1))
        self.policy = self._policy()

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _write_manifests(self) -> str:
        product = demo_identity("v0.7.0", "a" * 40).product
        schema = {"fingerprint": "b" * 64}
        seed_binding = {
            "manifest_version": 1,
            "runtime_contract": RUNTIME_CONTRACT,
            "product": product,
            "schema": schema,
            "fixture_catalog": {
                "version": FIXTURE_CATALOG_VERSION,
                "revision": FIXTURE_CATALOG_REVISION,
                "demo_matrix_version": DEMO_MATRIX_VERSION,
            },
            "fixture_profile": {
                "name": "public-demo",
                "reference_time": "2026-01-01T00:00:00+00:00",
                "scenarios": ["demo.487.absence", "demo.487.planchange"],
                **PUBLIC_DEMO_RUNTIME,
            },
        }
        seed_revision = canonical_digest(seed_binding)
        self.app_manifest.write_text(
            json.dumps(
                {
                    "manifest_version": 1,
                    "runtime_contract": RUNTIME_CONTRACT,
                    "product": product,
                    "schema": schema,
                    "seed_revision": seed_revision,
                }
            ),
            encoding="utf-8",
        )
        self.seed_manifest.write_text(
            json.dumps({**seed_binding, "seed_revision": seed_revision}), encoding="utf-8"
        )
        (self.root / "demo-runtime-status.json").write_text(
            json.dumps(
                {
                    "initialized": True,
                    "initialization_status": "ready",
                    "initialized_at": "2026-08-14T01:00:00+00:00",
                    "last_reset_at": "2026-08-14T01:00:00+00:00",
                    "seed_revision": seed_revision,
                }
            ),
            encoding="utf-8",
        )
        return seed_revision

    def _policy(self, *, capacity: int = 32, suffix: str = "workspaces") -> DemoRuntimePolicy:
        policy = DemoRuntimePolicy(
            self.app_manifest,
            self.seed_manifest,
            workspace_dir=self.root / suffix,
            capacity=capacity,
            clock=self.clock,
        )
        DemoTestHandler.runtime_policy = policy
        return policy

    @staticmethod
    def _client(api: ApiServer) -> TestClient:
        if api.client is None:
            raise AssertionError("Test client is not running")
        return api.client

    @staticmethod
    def _csrf(client: TestClient) -> dict[str, str]:
        token = client.cookies.get("lzug_csrf")
        return {"X-CSRF-Token": token} if token else {}

    def _write(
        self,
        client: TestClient,
        method: str,
        path: str,
        payload: dict | None = None,
    ):
        return client.request(method, path, json=payload, headers=self._csrf(client))

    def _role(self, client: TestClient, role: str):
        response = self._write(client, "POST", "/api/demo/session", {"role": role})
        self.assertEqual(HTTPStatus.CREATED, response.status_code, response.text)
        return response

    def _workspace_path(self, db_path: Path, client: TestClient) -> Path:
        workspace = self.policy.workspaces.resolve(db_path, client.cookies.get("lzug_session"))
        self.assertIsNotNone(workspace)
        assert workspace is not None
        return workspace.path

    @staticmethod
    def _items(client: TestClient, path: str) -> list[dict]:
        response = client.get(path)
        if response.status_code != HTTPStatus.OK:
            raise AssertionError(response.text)
        return response.json()["items"]

    def _complete_absence(self, client: TestClient) -> None:
        self._role(client, "examiner")
        day_response = client.get(f"/api/confirmed-plan-days/{ABSENCE_DAY_ID}")
        self.assertEqual(HTTPStatus.OK, day_response.status_code, day_response.text)
        day_revision = day_response.json()["day"]["revision"]
        report_response = self._write(
            client,
            "POST",
            "/api/absence-reports",
            {
                "exam_day_id": ABSENCE_DAY_ID,
                "exam_day_assignment_id": ABSENCE_ASSIGNMENT_ID,
                "day_revision": day_revision,
            },
        )
        self.assertEqual(HTTPStatus.CREATED, report_response.status_code, report_response.text)
        report = report_response.json()
        self.assertIsNone(report["reason"])
        self.assertEqual(
            [REPLACEMENT_MEMBER_ID],
            [item["committee_member_id"] for item in report["responses"]],
        )

        self._role(client, "replacement")
        reports = self._items(client, "/api/absence-reports")
        response = reports[0]["responses"][0]
        answer = self._write(
            client,
            "PATCH",
            f"/api/replacement-responses/{response['id']}",
            {"response": "available"},
        )
        self.assertEqual(HTTPStatus.OK, answer.status_code, answer.text)

        self._role(client, "chair")
        report = self._items(client, "/api/absence-reports")[0]
        selected = self._write(
            client,
            "POST",
            f"/api/absence-reports/{report['id']}/select-replacement",
            {"committee_member_id": REPLACEMENT_MEMBER_ID, "version": report["version"]},
        )
        self.assertEqual(HTTPStatus.OK, selected.status_code, selected.text)
        self.assertEqual("replacement_selected", selected.json()["status"])

    def _complete_plan_change(self, client: TestClient) -> None:
        self._role(client, "chair")
        overview = client.get("/api/demo/scenarios").json()
        prepared = overview["prepared_plan_change"]
        response = client.get(f"/api/exam-rounds/{ROUND_ID}/confirmed-plan")
        self.assertEqual(HTTPStatus.OK, response.status_code, response.text)
        plan = response.json()
        payload = {
            "round_id": plan["round_id"],
            "revision": plan["revision"],
            "exam_days": plan["exam_days"],
        }
        day = next(item for item in payload["exam_days"] if item["id"] == prepared["day_id"])
        day["room_id"] = prepared["target_location_id"]
        day["location_id"] = prepared["target_location_id"]
        assignment = next(
            item for item in day["assignments"] if item["id"] == prepared["assignment_id"]
        )
        assignment["committee_member_id"] = prepared["replacement_member_id"]
        payload["reason"] = prepared["reason"]
        saved = self._write(client, "PUT", f"/api/exam-rounds/{ROUND_ID}/confirmed-plan", payload)
        self.assertEqual(HTTPStatus.OK, saved.status_code, saved.text)
        self.assertEqual(2, saved.json()["revision"])
        self.assertEqual("succeeded", saved.json()["consequence_status"]["derivation_status"])

    def test_public_status_roles_capabilities_and_fixed_lifetime(self) -> None:
        with (
            TempDatabase(seed_sql=public_demo_seed_sql()) as db_path,
            ApiServer(db_path, DemoTestHandler) as api,
        ):
            client = self._client(api)
            status = client.get("/api/demo/status")
            self.assertEqual(HTTPStatus.OK, status.status_code)
            self.assertEqual(self.seed_revision, status.json()["seed_revision"])
            self.assertEqual(DEMO_MATRIX_VERSION, status.json()["demo_matrix_version"])
            self.assertEqual("Europe/Berlin", status.json()["reset_timezone"])

            created = self._role(client, "examiner").json()
            self.assertEqual("Peter Quince", created["display_name"])
            session = client.get("/api/session").json()
            self.assertEqual("examiner", session["demo_role"])
            self.assertEqual(sorted(ROLE_CAPABILITIES["examiner"]), session["capabilities"])
            original_expiry = session["demo_workspace_expires_at"]
            self.assertNotIn(str(self._workspace_path(db_path, client)), json.dumps(session))

            self.clock.advance(timedelta(minutes=17))
            switched = self._role(client, "replacement").json()
            self.assertEqual("Francis Flute", switched["display_name"])
            replacement_session = client.get("/api/session").json()
            self.assertEqual(original_expiry, replacement_session["demo_workspace_expires_at"])
            self.assertEqual(
                sorted(ROLE_CAPABILITIES["replacement"]), replacement_session["capabilities"]
            )
            overview = client.get("/api/demo/scenarios").json()
            self.assertLessEqual(overview["remaining_seconds"], 43 * 60)
            self.assertEqual(2, len(overview["scenarios"]))

            with TestClient(client.app, base_url="http://127.0.0.1") as anonymous:
                rejected = anonymous.post("/api/demo/session", json={"role": "operator"})
            self.assertEqual(HTTPStatus.BAD_REQUEST, rejected.status_code)
            login = client.post(
                "/api/auth/login",
                json={
                    "email": "chair@demo.lzug.invalid",
                    "password": "x",
                    "second_factor": "x",
                },
            )
            self.assertEqual(HTTPStatus.FORBIDDEN, login.status_code)
            rotate = self._write(client, "POST", "/api/session/rotate", {})
            self.assertEqual(HTTPStatus.FORBIDDEN, rotate.status_code)

    def test_chair_session_starts_from_canonical_built_seed(self) -> None:
        artifact_root = self.root / "canonical-seed"
        seed_database = artifact_root / "seed.sqlite"
        seed_manifest = artifact_root / "seed.json"
        runtime_root = self.root / "canonical-runtime"
        product_tag = "v0.7.0"
        product_commit = "c" * 40
        seed = build_seed(
            Path("."),
            seed_database,
            seed_manifest,
            product_tag=product_tag,
            product_commit=product_commit,
        )
        initialize_workdir(seed_database, seed_manifest, runtime_root)
        app_manifest = runtime_root / "app.json"
        build_app_manifest(
            Path("."),
            app_manifest,
            product_tag=product_tag,
            product_commit=product_commit,
            seed_revision=seed["seed_revision"],
        )
        self.app_manifest = app_manifest
        self.seed_manifest = runtime_root / "demo-seed-manifest.json"
        self.policy = self._policy(suffix="canonical-workspaces")

        with ApiServer(runtime_root / "lzug.sqlite", DemoTestHandler) as api:
            response = self._client(api).post("/api/demo/session", json={"role": "chair"})

        self.assertEqual(HTTPStatus.CREATED, response.status_code, response.text)

    def test_role_switch_and_reset_require_csrf(self) -> None:
        with (
            TempDatabase(seed_sql=public_demo_seed_sql()) as db_path,
            ApiServer(db_path, DemoTestHandler) as api,
        ):
            client = self._client(api)
            self._role(client, "examiner")
            self.assertEqual(
                HTTPStatus.FORBIDDEN,
                client.post("/api/demo/session", json={"role": "chair"}).status_code,
            )
            self.assertEqual(
                HTTPStatus.FORBIDDEN, client.post("/api/demo/reset", json={}).status_code
            )

    def test_failed_session_creation_releases_the_unbound_workspace(self) -> None:
        with (
            TempDatabase(seed_sql=public_demo_seed_sql()) as db_path,
            ApiServer(db_path, DemoTestHandler) as api,
        ):
            with session_scope(db_path) as session:
                account = session.get(UserAccount, 1)
                assert account is not None
                session.delete(account)

            client = self._client(api)
            response = client.post("/api/demo/session", json={"role": "chair"})

            self.assertEqual(HTTPStatus.SERVICE_UNAVAILABLE, response.status_code)
            self.assertIsNone(client.cookies.get("lzug_session"))
            self.assertEqual(0, self.policy.workspaces.active_count(db_path))
            self.assertEqual([], list(self.policy.workspaces.root.glob("workspace-*.sqlite*")))

    def test_isolation_capacity_reset_logout_expiry_and_system_reset(self) -> None:
        self.policy = self._policy(capacity=2, suffix="isolation")
        with (
            TempDatabase(seed_sql=public_demo_seed_sql()) as db_path,
            ApiServer(db_path, DemoTestHandler) as api,
        ):
            first = self._client(api)
            with TestClient(first.app, base_url="http://127.0.0.1") as second:
                self._role(first, "examiner")
                self._role(second, "examiner")
                first_path = self._workspace_path(db_path, first)
                second_path = self._workspace_path(db_path, second)
                self.assertNotEqual(first_path, second_path)
                self.assertEqual(0o700, self.policy.workspaces.root.stat().st_mode & 0o777)
                self.assertEqual(0o600, first_path.stat().st_mode & 0o777)

                day = first.get(f"/api/confirmed-plan-days/{ABSENCE_DAY_ID}").json()["day"]
                result = self._write(
                    first,
                    "POST",
                    "/api/absence-reports",
                    {
                        "exam_day_id": ABSENCE_DAY_ID,
                        "exam_day_assignment_id": ABSENCE_ASSIGNMENT_ID,
                        "day_revision": day["revision"],
                    },
                )
                self.assertEqual(HTTPStatus.CREATED, result.status_code, result.text)
                self.assertEqual([], self._items(second, "/api/absence-reports"))

                old_token = first.cookies.get("lzug_session")
                old_csrf = first.cookies.get("lzug_csrf")
                reset = self._write(first, "POST", "/api/demo/reset", {})
                self.assertEqual(HTTPStatus.OK, reset.status_code, reset.text)
                self.assertEqual("examiner", reset.json()["role"])
                self.assertEqual([], self._items(first, "/api/absence-reports"))
                progress = first.get("/api/demo/scenarios").json()["scenarios"]
                self.assertEqual([0, 0], [item["completed_steps"] for item in progress])
                with TestClient(first.app, base_url="http://127.0.0.1") as stale:
                    stale.cookies.set("lzug_session", old_token)
                    stale.cookies.set("lzug_csrf", old_csrf)
                    self.assertEqual(HTTPStatus.UNAUTHORIZED, stale.get("/api/session").status_code)

                os.utime(
                    db_path,
                    ns=(db_path.stat().st_atime_ns, db_path.stat().st_mtime_ns + 1),
                )
                self.assertEqual(HTTPStatus.UNAUTHORIZED, first.get("/api/session").status_code)
                self.assertFalse(first_path.exists())

                self._role(first, "chair")
                logout_path = self._workspace_path(db_path, first)
                logout = self._write(first, "POST", "/api/session/logout", {})
                self.assertEqual(HTTPStatus.NO_CONTENT, logout.status_code)
                self.assertFalse(logout_path.exists())
                self.assertEqual([], list(logout_path.parent.glob(f"{logout_path.name}*")))

                self._role(second, "chair")
                expired_path = self._workspace_path(db_path, second)
                self.clock.advance(timedelta(minutes=60, seconds=1))
                self.assertEqual(HTTPStatus.UNAUTHORIZED, second.get("/api/session").status_code)
                self.assertFalse(expired_path.exists())
                self.assertEqual([], list(expired_path.parent.glob(f"{expired_path.name}*")))

        self.policy = self._policy(capacity=1, suffix="capacity")
        with (
            TempDatabase(seed_sql=public_demo_seed_sql()) as db_path,
            ApiServer(db_path, DemoTestHandler) as api,
        ):
            first = self._client(api)
            with TestClient(first.app, base_url="http://127.0.0.1") as second:
                self._role(first, "chair")
                unavailable = second.post("/api/demo/session", json={"role": "chair"})
                self.assertEqual(HTTPStatus.SERVICE_UNAVAILABLE, unavailable.status_code)
                self.assertIsNone(second.cookies.get("lzug_session"))
                self.assertEqual(1, self.policy.workspaces.active_count(db_path))

    def test_both_scenarios_work_in_either_order_and_reset_together(self) -> None:
        with (
            TempDatabase(seed_sql=public_demo_seed_sql()) as db_path,
            ApiServer(db_path, DemoTestHandler) as api,
        ):
            client = self._client(api)
            self._role(client, "chair")
            workspace_path = self._workspace_path(db_path, client)
            with session_scope(workspace_path) as session:
                initial = {
                    (event.exam_day_assignment_id, event.recipient_member_id): (
                        event.external_event_id,
                        event.version,
                        event.status,
                        event.location,
                    )
                    for event in session.scalars(select(CalendarEvent)).all()
                }

            self._complete_plan_change(client)
            self._complete_absence(client)
            statuses = client.get("/api/demo/scenarios").json()["scenarios"]
            self.assertEqual(["complete", "complete"], [item["status"] for item in statuses])
            self._assert_effects(workspace_path, initial)
            self._assert_own_views(client)

            reset = self._write(client, "POST", "/api/demo/reset", {})
            self.assertEqual(HTTPStatus.OK, reset.status_code)
            self.assertEqual([], self._items(client, "/api/notifications"))
            statuses = client.get("/api/demo/scenarios").json()["scenarios"]
            self.assertEqual(["ready", "ready"], [item["status"] for item in statuses])
            self._complete_absence(client)
            self._complete_plan_change(client)
            statuses = client.get("/api/demo/scenarios").json()["scenarios"]
            self.assertEqual(["complete", "complete"], [item["status"] for item in statuses])

    def _assert_effects(self, workspace_path: Path, initial: dict) -> None:
        with session_scope(workspace_path) as session:
            events = session.scalars(select(CalendarEvent).order_by(CalendarEvent.id)).all()
            deliveries = session.scalars(select(NotificationDelivery)).all()
            revisions = session.scalars(select(ConfirmedPlanRevision)).all()
            self.assertEqual([], deliveries)
            self.assertEqual(1, len(revisions))

            def matching(assignment_id: int, member_id: int) -> list[CalendarEvent]:
                return [
                    item
                    for item in events
                    if item.exam_day_assignment_id == assignment_id
                    and item.recipient_member_id == member_id
                ]

            absence_old = matching(ABSENCE_ASSIGNMENT_ID, 3)[0]
            self.assertEqual("cancelled", absence_old.status)
            self.assertEqual(initial[(ABSENCE_ASSIGNMENT_ID, 3)][0], absence_old.external_event_id)
            self.assertGreater(absence_old.version, initial[(ABSENCE_ASSIGNMENT_ID, 3)][1])
            absence_new = matching(ABSENCE_ASSIGNMENT_ID, REPLACEMENT_MEMBER_ID)[0]
            self.assertNotEqual(absence_old.external_event_id, absence_new.external_event_id)

            plan_old = matching(PLAN_CHANGE_ASSIGNMENT_ID, 3)[0]
            plan_new = matching(PLAN_CHANGE_ASSIGNMENT_ID, PLAN_REPLACEMENT_MEMBER_ID)[0]
            self.assertEqual("cancelled", plan_old.status)
            self.assertNotEqual(plan_old.external_event_id, plan_new.external_event_id)
            chair_event = matching(PLAN_CHANGE_ASSIGNMENT_START_ID, 1)[0]
            self.assertEqual(
                initial[(PLAN_CHANGE_ASSIGNMENT_START_ID, 1)][0], chair_event.external_event_id
            )
            self.assertGreater(
                chair_event.version, initial[(PLAN_CHANGE_ASSIGNMENT_START_ID, 1)][1]
            )
            self.assertNotEqual(
                initial[(PLAN_CHANGE_ASSIGNMENT_START_ID, 1)][3], chair_event.location
            )
            unaffected = matching(ABSENCE_ASSIGNMENT_START_ID, 1)[0]
            self.assertEqual(
                initial[(ABSENCE_ASSIGNMENT_START_ID, 1)],
                (
                    unaffected.external_event_id,
                    unaffected.version,
                    unaffected.status,
                    unaffected.location,
                ),
            )

    def _assert_own_views(self, client: TestClient) -> None:
        member_by_role = {"chair": 1, "examiner": 3, "replacement": REPLACEMENT_MEMBER_ID}
        for role, member_id in member_by_role.items():
            with self.subTest(role=role):
                self._role(client, role)
                notifications = self._items(client, "/api/notifications")
                events = self._items(client, "/api/calendar/events")
                self.assertTrue(notifications)
                self.assertTrue(events)
                for event in events:
                    download = client.get(event["download_url"])
                    self.assertEqual(HTTPStatus.OK, download.status_code)
                    self.assertIn("BEGIN:VCALENDAR", download.text)
                    self.assertIn(event["external_event_id"], download.text)
                with session_scope(self._workspace_path_for_client(client)) as session:
                    own_ids = set(
                        session.scalars(
                            select(Notification.id).where(
                                Notification.recipient_member_id == member_id
                            )
                        ).all()
                    )
                self.assertEqual(own_ids, {item["id"] for item in notifications})

        self._role(client, "chair")
        with session_scope(self._workspace_path_for_client(client)) as session:
            replacement_event_id = session.scalar(
                select(CalendarEvent.id).where(
                    CalendarEvent.recipient_member_id == REPLACEMENT_MEMBER_ID
                )
            )
        assert replacement_event_id is not None
        self.assertEqual(
            HTTPStatus.NOT_FOUND,
            client.get(f"/api/calendar/events/{replacement_event_id}.ics").status_code,
        )
        channels = client.get("/api/notification-channels").json()
        self.assertEqual(
            {
                "web_push": {"available": False, "public_key": None},
                "email_fallback_configured": False,
                "sink_enabled": False,
            },
            channels,
        )
        self.assertEqual([], self._items(client, "/api/notification-overview"))

    def _workspace_path_for_client(self, client: TestClient) -> Path:
        assert self.policy.base_db_path is not None
        return self._workspace_path(self.policy.base_db_path, client)

    def test_allowlist_negative_paths_idempotency_and_plan_conflict(self) -> None:
        with (
            TempDatabase(seed_sql=public_demo_seed_sql()) as db_path,
            ApiServer(db_path, DemoTestHandler) as api,
        ):
            client = self._client(api)
            self._role(client, "examiner")
            day = client.get(f"/api/confirmed-plan-days/{ABSENCE_DAY_ID}").json()["day"]
            base_report = {
                "exam_day_id": ABSENCE_DAY_ID,
                "exam_day_assignment_id": ABSENCE_ASSIGNMENT_ID,
                "day_revision": day["revision"],
            }
            for payload in (
                {**base_report, "reason": "not allowed"},
                {**base_report, "exam_day_assignment_id": 1},
                {**base_report, "exam_day_id": PLAN_CHANGE_DAY_ID},
            ):
                self.assertEqual(
                    HTTPStatus.FORBIDDEN,
                    self._write(client, "POST", "/api/absence-reports", payload).status_code,
                )
            with TestClient(client.app, base_url="http://127.0.0.1") as anonymous:
                unauthenticated = anonymous.post("/api/absence-reports", json=base_report)
            self.assertEqual(HTTPStatus.UNAUTHORIZED, unauthenticated.status_code)
            created = self._write(client, "POST", "/api/absence-reports", base_report)
            self.assertEqual(HTTPStatus.CREATED, created.status_code)
            self.assertEqual(
                HTTPStatus.FORBIDDEN,
                self._write(client, "POST", "/api/absence-reports", base_report).status_code,
            )

            report = created.json()
            response_id = report["responses"][0]["id"]
            self._role(client, "replacement")
            self.assertEqual(
                HTTPStatus.FORBIDDEN,
                self._write(
                    client,
                    "PATCH",
                    f"/api/replacement-responses/{response_id}",
                    {"response": "unavailable"},
                ).status_code,
            )
            self.assertEqual(
                HTTPStatus.FORBIDDEN,
                self._write(
                    client,
                    "POST",
                    f"/api/replacement-responses/{response_id}/respond",
                    {"response": "available"},
                ).status_code,
            )
            self.assertEqual(
                HTTPStatus.OK,
                self._write(
                    client,
                    "PATCH",
                    f"/api/replacement-responses/{response_id}",
                    {"response": "available"},
                ).status_code,
            )
            self.assertEqual(
                HTTPStatus.FORBIDDEN,
                self._write(
                    client,
                    "PATCH",
                    f"/api/replacement-responses/{response_id}",
                    {"response": "available"},
                ).status_code,
            )

            self._role(client, "chair")
            report = self._items(client, "/api/absence-reports")[0]
            for member_id in (7, 8):
                self.assertEqual(
                    HTTPStatus.FORBIDDEN,
                    self._write(
                        client,
                        "POST",
                        f"/api/absence-reports/{report['id']}/select-replacement",
                        {"committee_member_id": member_id, "version": report["version"]},
                    ).status_code,
                )
            self.assertEqual(
                HTTPStatus.FORBIDDEN,
                self._write(client, "POST", "/api/calendar/feed", {"rotate": False}).status_code,
            )
            self.assertEqual(
                HTTPStatus.FORBIDDEN,
                self._write(client, "PATCH", "/api/exam-rounds/2", {"name": "x"}).status_code,
            )

            plan = client.get(f"/api/exam-rounds/{ROUND_ID}/confirmed-plan").json()
            prepared = client.get("/api/demo/scenarios").json()["prepared_plan_change"]
            stale_payload = {
                "round_id": plan["round_id"],
                "revision": plan["revision"],
                "exam_days": plan["exam_days"],
                "reason": prepared["reason"],
            }
            target_day = next(
                item for item in stale_payload["exam_days"] if item["id"] == PLAN_CHANGE_DAY_ID
            )
            target_day["room_id"] = TARGET_LOCATION_ID
            target_day["location_id"] = TARGET_LOCATION_ID
            next(
                item
                for item in target_day["assignments"]
                if item["id"] == PLAN_CHANGE_ASSIGNMENT_ID
            )["committee_member_id"] = PLAN_REPLACEMENT_MEMBER_ID

            with TestClient(client.app, base_url="http://127.0.0.1") as second_tab:
                second_tab.cookies.update(client.cookies)
                first = self._write(
                    client,
                    "PUT",
                    f"/api/exam-rounds/{ROUND_ID}/confirmed-plan",
                    stale_payload,
                )
                self.assertEqual(HTTPStatus.OK, first.status_code, first.text)
                stale = self._write(
                    second_tab,
                    "PUT",
                    f"/api/exam-rounds/{ROUND_ID}/confirmed-plan",
                    stale_payload,
                )
                self.assertEqual(HTTPStatus.CONFLICT, stale.status_code, stale.text)
            workspace_path = self._workspace_path(db_path, client)
            with session_scope(workspace_path) as session:
                self.assertEqual(1, len(session.scalars(select(ConfirmedPlanRevision)).all()))

    def test_started_assignment_is_rejected_by_product_guard(self) -> None:
        with (
            TempDatabase(seed_sql=public_demo_seed_sql()) as db_path,
            ApiServer(db_path, DemoTestHandler) as api,
        ):
            client = self._client(api)
            self._role(client, "examiner")
            workspace_path = self._workspace_path(db_path, client)
            with session_scope(workspace_path) as session:
                slot = session.scalar(
                    select(ExamSlot).where(ExamSlot.exam_day_id == ABSENCE_DAY_ID)
                )
                assert slot is not None
                previous_day = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
                slot.starts_at = f"{previous_day} 08:30:00"
            day = client.get(f"/api/confirmed-plan-days/{ABSENCE_DAY_ID}").json()["day"]
            response = self._write(
                client,
                "POST",
                "/api/absence-reports",
                {
                    "exam_day_id": ABSENCE_DAY_ID,
                    "exam_day_assignment_id": ABSENCE_ASSIGNMENT_ID,
                    "day_revision": day["revision"],
                },
            )
            self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)
            self.assertEqual([], self._items(client, "/api/absence-reports"))

    def test_relative_seed_handles_year_and_clock_change_boundaries(self) -> None:
        instants = (
            datetime(2026, 3, 28, 22, 30, tzinfo=UTC),
            datetime(2026, 10, 24, 22, 30, tzinfo=UTC),
            datetime(2026, 12, 31, 10, 0, tzinfo=UTC),
        )
        for instant in instants:
            with (
                self.subTest(instant=instant.isoformat()),
                TempDatabase(seed_sql=public_demo_seed_sql()) as db_path,
            ):
                seed_demo_scenarios(db_path, instant)
                with session_scope(db_path) as session:
                    absence = session.get(ExamDay, ABSENCE_DAY_ID)
                    plan = session.get(ExamDay, PLAN_CHANGE_DAY_ID)
                    assert absence is not None and plan is not None
                    absence_date = datetime.fromisoformat(absence.date).date()
                    plan_date = datetime.fromisoformat(plan.date).date()
                    self.assertEqual(timedelta(days=8), plan_date - absence_date)
                    start = datetime.combine(absence_date, time(8, 30), TIME_ZONE).astimezone(UTC)
                    self.assertGreater(start, instant)
                    self.assertLess(start - instant, timedelta(hours=48))
                    self.assertEqual(_closest_relative_exam_date(instant), absence_date)

    def test_seed_and_matrix_mismatches_fail_closed(self) -> None:
        manifest = json.loads(self.seed_manifest.read_text(encoding="utf-8"))
        manifest["fixture_catalog"]["demo_matrix_version"] = "demo-paths-stale"
        binding = {key: value for key, value in manifest.items() if key != "seed_revision"}
        manifest["seed_revision"] = canonical_digest(binding)
        self.seed_manifest.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(
            DemoArtifactError, "fixture catalog does not match the demo matrix"
        ):
            DemoRuntimePolicy(self.app_manifest, self.seed_manifest)

        with TempDatabase(seed_sql=public_demo_seed_sql()) as db_path:
            with session_scope(db_path) as session:
                account = session.get(UserAccount, 4)
                assert account is not None
                session.delete(account)
            with ApiServer(db_path, DemoTestHandler) as api:
                response = self._client(api).post("/api/demo/session", json={"role": "replacement"})
            self.assertEqual(HTTPStatus.SERVICE_UNAVAILABLE, response.status_code)
            self.assertEqual({"error": "Demo role is unavailable."}, response.json())

    def test_matrix_contracts_are_unique_and_capability_aligned(self) -> None:
        contracts = (*DEMO_READ_MATRIX, *DEMO_MUTATION_MATRIX)
        self.assertEqual(len(contracts), len({item.name for item in contracts}))
        self.assertEqual({"chair", "examiner", "replacement"}, set(DEMO_ROLES))
        self.assertEqual(
            {
                "absence:coordinate",
                "absence:write-own",
                "absence:respond-own",
                "confirmed-plan:revise",
                "notifications:read-own",
                "calendar:read-own",
            },
            set().union(*ROLE_CAPABILITIES.values()),
        )
        for contract in contracts:
            with self.subTest(contract=contract.name):
                self.assertTrue(contract.visible)
                self.assertTrue(contract.allowed)
                self.assertTrue(contract.domain_authorization)
                for role in contract.roles:
                    self.assertIn(contract.capability, ROLE_CAPABILITIES[role])

    def test_exam_venue_mutations_remain_fail_closed_in_the_demo(self) -> None:
        with (
            TempDatabase(seed_sql=public_demo_seed_sql()) as db_path,
            ApiServer(db_path, DemoTestHandler) as api,
        ):
            client = self._client(api)
            self._role(client, "chair")
            requests = (
                ("POST", "/api/exam-venues", {"name": "Nicht anlegen"}),
                ("POST", "/api/exam-venues/duplicate-check", {}),
                (
                    "PATCH",
                    "/api/exam-venues/1",
                    {"expected_revision": 1, "is_active": False},
                ),
                ("DELETE", "/api/exam-venues/1", {"expected_revision": 1}),
                ("POST", "/api/exam-venues/1/geocode", {"expected_revision": 1}),
                ("POST", "/api/exam-venues/1/change-impact", {}),
                ("POST", "/api/exam-venues/1/rooms", {"name": "Nicht anlegen"}),
                ("PATCH", "/api/exam-rooms/1", {"expected_revision": 1}),
                ("DELETE", "/api/exam-rooms/1", {"expected_revision": 1}),
                ("POST", "/api/exam-rooms/1/change-impact", {}),
                ("POST", "/api/exam-venues/1/contacts", {"label": "Nicht anlegen"}),
                ("PATCH", "/api/exam-venue-contacts/1", {"expected_revision": 1}),
                ("DELETE", "/api/exam-venue-contacts/1", {"expected_revision": 1}),
                ("POST", "/api/exam-venue-changes/1/consequences/retry", {}),
                (
                    "POST",
                    "/api/exam-venues/1/promotion-requests",
                    {"expected_revision": 1, "reason": "Nicht beantragen"},
                ),
                (
                    "POST",
                    "/api/exam-venue-promotion-requests/1/decision",
                    {"decision": "approve", "reason": "Nicht freigeben"},
                ),
            )

            for method, path, payload in requests:
                with self.subTest(method=method, path=path):
                    response = self._write(client, method, path, payload)
                    self.assertEqual(HTTPStatus.FORBIDDEN, response.status_code, response.text)


if __name__ == "__main__":
    unittest.main()
