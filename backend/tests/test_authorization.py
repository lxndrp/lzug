from __future__ import annotations

import unittest
from http import HTTPStatus

from backend.auth import AuthenticationRepository
from backend.models import (
    CANDIDATE_EXAM_DAY,
    COMMITTEE,
    COMMITTEE_MEMBER,
    EXAM_ROUND,
    PERSON,
)
from backend.planning import PlanningService
from backend.repositories import ResourceRepository
from backend.tests.helpers import ApiServer, TempDatabase, assert_status


class AuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = TempDatabase()
        self.db_path = self.database.__enter__()
        self.repository = ResourceRepository(self.db_path)
        self.authentication = AuthenticationRepository(self.db_path)

        committee = self.repository.create(
            COMMITTEE, {"name": "Prüfungsausschuss Teststadt 2", "occupation": "FI"}
        )
        self.committee_id = committee["id"]
        self.members: dict[int, int] = {}
        for person_number, status, role in (
            (9, "ordinary", "chair"),
            (10, "ordinary", "deputy_chair"),
            (11, "ordinary", "member"),
            (12, "deputy", "member"),
        ):
            person = self.repository.create(
                PERSON,
                {
                    "first_name": "Testperson",
                    "last_name": str(person_number),
                    "email": f"testperson.{person_number}@example.invalid",
                },
            )
            member = self.repository.create(
                COMMITTEE_MEMBER,
                {
                    "person_id": person["id"],
                    "committee_id": self.committee_id,
                    "member_status": status,
                    "committee_role": role,
                    "representing_side": "employer",
                    "is_active": 1,
                },
            )
            self.members[person_number] = member["id"]
            account = self.authentication.create_account(
                f"testperson.{person_number}@example.invalid", person_id=person["id"]
            )
            self.members[f"account-{person_number}"] = account["id"]

        exam_round = self.repository.create(
            EXAM_ROUND,
            {
                "exam_half_year_id": 1,
                "committee_id": self.committee_id,
                "name": "Winter 2026/27 · Ausschuss 2",
                "created_by_member_id": self.members[9],
            },
        )
        self.round_id = exam_round["id"]
        self.repository.create_candidate(
            {
                "first_name": "Prüfling",
                "last_name": "Ausschuss 2",
                "ihk_exam_number": "TEST-2026-0099",
                "specialization": "application_development",
                "training_company": "Testbetrieb 2",
                "exam_round_id": self.round_id,
            },
        )
        day = self.repository.create(
            CANDIDATE_EXAM_DAY,
            {"exam_round_id": self.round_id, "date": "2026-12-01", "is_active": 1},
        )
        self.repository.save_planning_settings(
            {
                "exam_round_id": self.round_id,
                "calendar_week_from": "2026-W49",
                "calendar_week_to": "2026-W49",
                "exams_per_day": 1,
                "max_exam_days_per_week": 1,
                "updated_by_member_id": self.members[9],
            }
        )
        self.availability_ids = {}
        for person_number in (11, 12):
            availability = self.repository.save_member_availability(
                {
                    "exam_round_id": self.round_id,
                    "committee_member_id": self.members[person_number],
                    "candidate_exam_day_id": day["id"],
                    "availability": "pending",
                }
            )
            self.availability_ids[person_number] = availability["id"]

    def tearDown(self) -> None:
        self.database.__exit__(None, None, None)

    def credentials(self, person_number: int):
        account_id = self.members[f"account-{person_number}"]
        return self.authentication.create_session(account_id)

    def test_member_lists_and_details_are_scoped_to_active_committees(self) -> None:
        with ApiServer(self.db_path) as api:
            status, committees = api.request("GET", "/api/committees")
            assert_status(status, HTTPStatus.OK)
            self.assertEqual([1], [item["id"] for item in committees["items"]])

            status, own = api.request(
                "GET", f"/api/exam-rounds/{self.round_id}", credentials=self.credentials(9)
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(self.committee_id, own["committee_id"])

            status, foreign = api.request(
                "GET", "/api/exam-rounds/1", credentials=self.credentials(9)
            )
            assert_status(status, HTTPStatus.NOT_FOUND)
            self.assertNotIn("Prüfungsausschuss Teststadt 1", str(foreign))

            status, candidates = api.request(
                "GET", "/api/candidates", credentials=self.credentials(9)
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual([13], [item["id"] for item in candidates["items"]])

    def test_chair_and_deputy_chair_have_the_same_management_rights(self) -> None:
        with ApiServer(self.db_path) as api:
            for person_number in (9, 10):
                status, settings = api.request(
                    "PATCH",
                    f"/api/planning-settings/{self.round_id}",
                    {"exams_per_day": 2, "updated_by_member_id": 999999},
                    credentials=self.credentials(person_number),
                )
                assert_status(status, HTTPStatus.OK)
                self.assertEqual(2, settings["exams_per_day"])
                self.assertEqual(self.members[person_number], settings["updated_by_member_id"])

    def test_planning_proposal_is_restricted_to_chair_and_deputy_without_disclosure(
        self,
    ) -> None:
        PlanningService(self.db_path).generate_proposal(1)
        deputy_account = self.authentication.create_account(
            "testperson.beta@example.invalid", person_id=2
        )
        member_account = self.authentication.create_account(
            "testperson.gamma@example.invalid", person_id=3
        )
        chair_credentials = self.authentication.create_session(1)
        deputy_credentials = self.authentication.create_session(deputy_account["id"])
        member_credentials = self.authentication.create_session(member_account["id"])
        foreign_chair_credentials = self.credentials(9)
        path = "/api/exam-rounds/1/planning-proposal"

        with ApiServer(self.db_path) as api:
            status, chair_proposal = api.request("GET", path, credentials=chair_credentials)
            assert_status(status, HTTPStatus.OK)

            status, deputy_proposal = api.request("GET", path, credentials=deputy_credentials)
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(chair_proposal, deputy_proposal)
            status, saved = api.request(
                "PUT", path, deputy_proposal, credentials=deputy_credentials
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(deputy_proposal["revision"] + 1, saved["revision"])

            for credentials in (member_credentials, foreign_chair_credentials):
                status, error = api.request("GET", path, credentials=credentials)
                assert_status(status, HTTPStatus.FORBIDDEN)
                self.assertEqual({"error": "Forbidden."}, error)
                status, error = api.request("PUT", path, saved, credentials=credentials)
                assert_status(status, HTTPStatus.FORBIDDEN)
                self.assertEqual({"error": "Forbidden."}, error)

            status, missing = api.request(
                "GET",
                "/api/exam-rounds/999999/planning-proposal",
                credentials=foreign_chair_credentials,
            )
            assert_status(status, HTTPStatus.FORBIDDEN)
            self.assertEqual({"error": "Forbidden."}, missing)

            for credentials in (member_credentials, foreign_chair_credentials):
                status, error = api.request(
                    "POST",
                    "/api/exam-rounds/1/confirm-plan",
                    {},
                    credentials=credentials,
                )
                assert_status(status, HTTPStatus.FORBIDDEN)
                self.assertEqual({"error": "Forbidden."}, error)

            status, confirmed = api.request(
                "POST",
                "/api/exam-rounds/1/confirm-plan",
                {},
                credentials=deputy_credentials,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("plan_confirmed", confirmed["status"])

    def test_member_status_does_not_change_member_rights_and_foreign_feedback_is_denied(
        self,
    ) -> None:
        with ApiServer(self.db_path) as api:
            for person_number in (11, 12):
                status, round_data = api.request(
                    "GET",
                    f"/api/exam-rounds/{self.round_id}",
                    credentials=self.credentials(person_number),
                )
                assert_status(status, HTTPStatus.OK)
                self.assertEqual(self.round_id, round_data["id"])

            status, own_feedback = api.request(
                "PATCH",
                f"/api/member-availabilities/{self.availability_ids[11]}",
                {"availability": "full_day", "committee_member_id": self.members[12]},
                credentials=self.credentials(11),
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(self.members[11], own_feedback["committee_member_id"])

            status, error = api.request(
                "PATCH",
                f"/api/member-availabilities/{self.availability_ids[12]}",
                {"availability": "full_day"},
                credentials=self.credentials(11),
            )
            assert_status(status, HTTPStatus.FORBIDDEN)
            self.assertEqual("Forbidden.", error["error"])

    def test_manipulated_committee_and_actor_ids_do_not_expand_access(self) -> None:
        with ApiServer(self.db_path) as api:
            status, error = api.request(
                "POST",
                "/api/exam-rounds",
                {
                    "exam_half_year_id": 1,
                    "committee_id": 1,
                    "name": "Foreign round",
                    "created_by_member_id": self.members[9],
                },
                credentials=self.credentials(9),
            )
            assert_status(status, HTTPStatus.FORBIDDEN)
            self.assertEqual("Forbidden.", error["error"])

    def test_inactive_membership_has_no_actor_scope(self) -> None:
        member_id = self.members[12]
        self.repository.update_membership(member_id, {"is_active": 0})
        with ApiServer(self.db_path) as api:
            status, error = api.request("GET", "/api/committees", credentials=self.credentials(12))
        assert_status(status, HTTPStatus.FORBIDDEN)
        self.assertEqual("Forbidden.", error["error"])
