from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from http import HTTPStatus
from threading import Barrier

from sqlalchemy import select

from backend.assessment.exam_results import ExamResultConflictError, ExamResultService
from backend.composition import authorization_service, exam_result_service
from backend.persistence.auth import SQLiteAuthenticationRepository
from backend.persistence.database import session_scope
from backend.persistence.execution import create_started_protocol
from backend.persistence.models import (
    CandidateExamAttendance,
    ExamDay,
    ExamDayAssignment,
    ExamResult,
    ExamRound,
    ExamSlot,
    ExternalExamResult,
    IndividualAssessment,
    MemberExamAttendance,
    ResultRetention,
)
from backend.tests.fixture_data import FIXTURE_ROOT, ORGANIZATION_NAMES
from backend.tests.helpers import ApiServer, TempDatabase, assert_status


def assessment_rules() -> dict:
    return {
        "components": [
            {
                "key": "documentation",
                "label": "Dokumentation",
                "mode": "independent",
                "weight": "20",
                "day_scoped": True,
                "required_assessors": 2,
                "max_deviation": "15",
                "additional_assessor_on_deviation": True,
                "criteria": [
                    {
                        "key": "quality",
                        "label": "Fachliche Qualität",
                        "raw_min": "0",
                        "raw_max": "10",
                        "weight": "100",
                    }
                ],
            },
            {
                "key": "presentation",
                "label": "Präsentation",
                "mode": "committee",
                "weight": "15",
                "day_scoped": True,
                "required_assessors": 3,
                "max_deviation": "15",
                "additional_assessor_on_deviation": False,
                "criteria": [
                    {
                        "key": "delivery",
                        "label": "Darstellung",
                        "raw_min": "0",
                        "raw_max": "10",
                        "weight": "100",
                    }
                ],
            },
            {
                "key": "discussion",
                "label": "Fachgespräch",
                "mode": "committee",
                "weight": "15",
                "day_scoped": True,
                "required_assessors": 3,
                "max_deviation": "15",
                "additional_assessor_on_deviation": False,
                "criteria": [
                    {
                        "key": "depth",
                        "label": "Fachliche Tiefe",
                        "raw_min": "0",
                        "raw_max": "10",
                        "weight": "100",
                    }
                ],
            },
        ],
        "external_areas": [
            {
                "key": "written",
                "label": "Schriftliches Eingangsergebnis",
                "weight": "50",
                "required": True,
            }
        ],
        "rounding": {
            "intermediate": {"mode": "none", "digits": None},
            "overall": {"mode": "half_up", "digits": 0},
            "threshold_basis": "unrounded",
        },
        "grades": [
            {"label": "sehr gut", "min_points": "92"},
            {"label": "gut", "min_points": "81"},
            {"label": "befriedigend", "min_points": "67"},
            {"label": "ausreichend", "min_points": "50"},
            {"label": "mangelhaft", "min_points": "30"},
            {"label": "ungenügend", "min_points": "0"},
        ],
        "passing": {
            "overall_min": "50",
            "component_minima": {},
            "external_minima": {"written": "30"},
        },
        "quorum": {"minimum_members": 3, "majority": "simple"},
    }


class ExamResultRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ExamResultService()
        self.rules = self.service._validate_rules(assessment_rules())

    def outcome(self, total: str, *, written: str = "82") -> dict:
        return self.service._outcome(
            self.rules,
            Decimal(total),
            {"documentation": Decimal("80"), "written": Decimal(written)},
        )

    def test_rounding_grade_and_passing_boundaries(self) -> None:
        below = self.outcome("49.99")
        self.assertEqual(Decimal("50"), below["rounded_total"])
        self.assertEqual(Decimal("49.99"), below["threshold_value"])
        self.assertEqual("mangelhaft", below["grade"])
        self.assertFalse(below["passed"])

        self.assertTrue(self.outcome("50")["passed"])
        self.assertTrue(self.outcome("50.01")["passed"])
        self.assertEqual("befriedigend", self.outcome("79.5")["grade"])
        self.assertEqual(Decimal("80"), self.outcome("79.5")["rounded_total"])

        grades = self.rules["grades"]
        for index, grade in enumerate(grades[:-1]):
            boundary = Decimal(grade["min_points"])
            with self.subTest(grade=grade["label"], position="on"):
                self.assertEqual(grade["label"], self.outcome(str(boundary))["grade"])
            with self.subTest(grade=grade["label"], position="above"):
                self.assertEqual(
                    grade["label"], self.outcome(str(boundary + Decimal("0.01")))["grade"]
                )
            with self.subTest(grade=grade["label"], position="below"):
                self.assertEqual(
                    grades[index + 1]["label"],
                    self.outcome(str(boundary - Decimal("0.01")))["grade"],
                )

        self.assertFalse(self.outcome("90", written="29.99")["passed"])
        self.assertTrue(self.outcome("90", written="30")["passed"])
        self.assertTrue(self.outcome("90", written="30.01")["passed"])

        rounded_threshold = assessment_rules()
        rounded_threshold["rounding"]["threshold_basis"] = "rounded"
        rounded_rules = self.service._validate_rules(rounded_threshold)
        outcome = self.service._outcome(
            rounded_rules,
            Decimal("49.5"),
            {"documentation": Decimal("80"), "written": Decimal("82")},
        )
        self.assertEqual(Decimal("50"), outcome["threshold_value"])
        self.assertTrue(outcome["passed"])

    def test_rejects_minima_assigned_to_the_wrong_area_kind(self) -> None:
        invalid = assessment_rules()
        invalid["passing"]["component_minima"] = {"written": "50"}
        invalid["passing"]["external_minima"] = {"documentation": "50"}
        with self.assertRaisesRegex(ValueError, "unbekannten Bereich"):
            self.service._validate_rules(invalid)

    def test_rule_models_preserve_strict_booleans_and_reject_shape_drift(self) -> None:
        invalid = assessment_rules()
        invalid["components"][0]["day_scoped"] = 1
        with self.assertRaisesRegex(ValueError, "bool"):
            self.service._validate_rules(invalid)

        invalid = assessment_rules()
        invalid["components"][0]["weight"] = True
        with self.assertRaisesRegex(ValueError, "Zahl"):
            self.service._validate_rules(invalid)

        invalid = assessment_rules()
        invalid["components"][0]["criteria"][0]["label"] = None
        with self.assertRaises(ValueError):
            self.service._validate_rules(invalid)

        invalid = assessment_rules()
        invalid["rounding"]["unexpected"] = "ignored?"
        with self.assertRaises(ValueError):
            self.service._validate_rules(invalid)

    def test_rule_models_keep_decimal_json_contract(self) -> None:
        normalized = self.service._validate_rules(assessment_rules())
        self.assertEqual("20", normalized["components"][0]["weight"])
        self.assertEqual("0", normalized["components"][0]["criteria"][0]["raw_min"])
        self.assertIsNone(normalized["rounding"]["intermediate"]["digits"])

    def test_declarative_field_constraints_preserve_numeric_and_shape_boundaries(self) -> None:
        for value in (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity"), True):
            invalid = assessment_rules()
            invalid["components"][0]["weight"] = value
            with self.subTest(weight=value), self.assertRaises(ValueError):
                self.service._validate_rules(invalid)

        for field_value in (None, "", "   "):
            invalid = assessment_rules()
            invalid["components"][0]["label"] = field_value
            with self.subTest(label=field_value), self.assertRaises(ValueError):
                self.service._validate_rules(invalid)

        invalid = assessment_rules()
        del invalid["components"][0]["weight"]
        with self.assertRaisesRegex(ValueError, "weight"):
            self.service._validate_rules(invalid)

        invalid = assessment_rules()
        invalid["components"][0]["criteria"].append(invalid["components"][0]["criteria"][0].copy())
        with self.assertRaisesRegex(ValueError, "eindeutig"):
            self.service._validate_rules(invalid)

        invalid = assessment_rules()
        invalid["components"][0]["criteria"][0]["weight"] = "49.99"
        with self.assertRaisesRegex(ValueError, "100 Prozent"):
            self.service._validate_rules(invalid)

    def test_weight_minimum_is_inclusive_for_components_and_criteria(self) -> None:
        rules = assessment_rules()
        rules["components"][0]["weight"] = "0.0000001"
        rules["components"][1]["weight"] = "34.9999999"
        criteria = rules["components"][0]["criteria"]
        criteria[0]["weight"] = "99.9999999"
        criteria.append(
            {
                **criteria[0],
                "key": "clarity",
                "label": "Klarheit",
                "weight": "0.0000001",
            }
        )

        normalized = self.service._validate_rules(rules)

        self.assertEqual(Decimal("0.0000001"), Decimal(normalized["components"][0]["weight"]))
        self.assertEqual(
            Decimal("0.0000001"),
            Decimal(normalized["components"][0]["criteria"][1]["weight"]),
        )


class ExamResultTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = TempDatabase()
        self.db_path = self.database.__enter__()
        authentication = SQLiteAuthenticationRepository(self.db_path)
        self.chair = authentication.create_session(1)
        self.examiner = authentication.create_session(2)
        outsider = authentication.create_account(
            "exam-result.outsider@example.invalid", person_id=4
        )
        operator = authentication.create_account(
            "exam-result.operator@example.invalid", is_operator=True
        )
        self.deputy = authentication.create_session(3)
        self.outsider = authentication.create_session(outsider["id"])
        self.operator = authentication.create_session(operator["id"])

        with session_scope(self.db_path) as session:
            exam_round = session.get(ExamRound, 1)
            exam_round.status = "plan_confirmed"
            day = ExamDay(
                exam_round_id=1,
                room_id=1,
                date="2026-11-16",
                status="confirmed",
                lunch_break_enabled=1,
                created_from_proposal=1,
            )
            session.add(day)
            session.flush()
            slot = ExamSlot(
                exam_day_id=day.id,
                round_candidate_id=1,
                slot_type="regular",
                starts_at="2026-11-16T09:00:00+01:00",
                ends_at="2026-11-16T10:00:00+01:00",
                sequence_number=1,
                status="confirmed",
                actual_started_at="2026-11-16T09:03:00+01:00",
                execution_status="running",
                status_changed_at="2026-11-16T09:03:00+01:00",
            )
            session.add(slot)
            session.flush()
            session.add_all(
                ExamDayAssignment(
                    exam_day_id=day.id,
                    committee_member_id=member_id,
                    assignment_role="examiner",
                    day_part="full_day",
                )
                for member_id in (1, 2, 3)
            )
            session.add(
                CandidateExamAttendance(
                    exam_slot_id=slot.id,
                    status="present",
                    arrived_at="2026-11-16T08:55:00+01:00",
                )
            )
            session.add_all(
                MemberExamAttendance(
                    exam_day_id=day.id,
                    committee_member_id=member_id,
                    status="present",
                    arrived_at="2026-11-16T08:45:00+01:00",
                )
                for member_id in (1, 2, 3)
            )
            protocol_id = create_started_protocol(
                session,
                slot_id=slot.id,
                participant_member_ids={1, 2, 3},
                created_by_member_id=1,
                created_at="2026-11-16T09:03:00+01:00",
            )
            self.day_id = day.id
            self.slot_id = slot.id
            self.protocol_id = protocol_id

    def tearDown(self) -> None:
        self.database.__exit__(None, None, None)

    @staticmethod
    def model_payload(*, version: int = 1, rules: dict | None = None) -> dict:
        return {
            "model_key": "fiae-final-2026",
            "version": version,
            "ihk": ORGANIZATION_NAMES[f"{FIXTURE_ROOT}.organization.athen"],
            "occupation": "Fachinformatiker/in",
            "specialization": None,
            "training_regulation": "Test-Ausbildungsordnung 2020",
            "exam_regulation": "Test-Prüfungsordnung 2026",
            "ihk_guidelines": "Verbindliche Test-Richtlinie 2026",
            "valid_from": "2026-01-01",
            "valid_until": "2026-12-31",
            "official_scale_min": "0",
            "official_scale_max": "100",
            "rules": rules or assessment_rules(),
            "retention_rule_reference": "PrüfO Teststadt § 31",
            "retention_years": 15,
        }

    def prepare_result(self, api: ApiServer, *, rules: dict | None = None) -> dict:
        status, model = api.request(
            "POST",
            "/api/assessment-model-versions",
            self.model_payload(rules=rules),
            credentials=self.chair,
        )
        assert_status(status, HTTPStatus.CREATED)
        status, _binding = api.request(
            "POST",
            "/api/exam-rounds/1/assessment-model-binding",
            {
                "assessment_model_version_id": model["id"],
                "reason": "Verbindliche Festlegung vor Bewertungsbeginn",
            },
            credentials=self.chair,
        )
        assert_status(status, HTTPStatus.OK)
        status, result = api.request(
            "GET",
            f"/api/confirmed-plan-days/{self.day_id}/slots/{self.slot_id}/result",
            credentials=self.chair,
        )
        assert_status(status, HTTPStatus.OK)
        return result

    def test_slot_result_rejects_slot_from_another_day_of_same_candidate(self) -> None:
        with ApiServer(self.db_path) as api:
            self.prepare_result(api)
            with session_scope(self.db_path) as session:
                other_day = ExamDay(
                    exam_round_id=1,
                    room_id=1,
                    date="2026-11-17",
                    status="confirmed",
                    lunch_break_enabled=1,
                    created_from_proposal=1,
                )
                session.add(other_day)
                session.flush()
                session.add(
                    ExamSlot(
                        exam_day_id=other_day.id,
                        round_candidate_id=1,
                        slot_type="mep",
                        starts_at="2026-11-17T09:00:00+01:00",
                        ends_at="2026-11-17T10:00:00+01:00",
                        sequence_number=1,
                        status="confirmed",
                    )
                )
                other_day_id = other_day.id

            status, _ = api.request(
                "GET",
                f"/api/confirmed-plan-days/{other_day_id}/slots/{self.slot_id}/result",
                credentials=self.chair,
            )

        assert_status(status, HTTPStatus.NOT_FOUND)

    def test_day_completion_preserves_legacy_result_without_model_binding(self) -> None:
        with session_scope(self.db_path) as session:
            session.add(
                ExamResult(
                    round_candidate_id=1,
                    source="migration",
                    legacy_status="no_result_data_in_lzug",
                )
            )

        with ApiServer(self.db_path) as api:
            status, completion = api.request(
                "GET",
                f"/api/confirmed-plan-days/{self.day_id}/result-completion",
                credentials=self.chair,
            )

        assert_status(status, HTTPStatus.OK)
        slot = completion["slots"][0]
        self.assertEqual("no_result_data_in_lzug", slot["state"])
        self.assertTrue(slot["regular_close_ready"])

    def test_external_result_preserves_text_limits_and_requires_replacement_reason(self) -> None:
        with ApiServer(self.db_path) as api:
            result = self.prepare_result(api)
            payload = {
                "version": result["version"],
                "area_key": "written",
                "points": "82",
                "professional_status": "p" * 300,
                "determining_authority": "a" * 500,
                "source_reference": "Bescheid TEST-2026-0001",
            }
            status, result = api.request(
                "POST",
                f"/api/exam-results/{result['id']}/external-results",
                payload,
                credentials=self.chair,
            )
            self.assertEqual(HTTPStatus.OK, status, result)
            self.assertEqual("p" * 300, result["external_results"][0]["professional_status"])
            self.assertEqual("a" * 500, result["external_results"][0]["determining_authority"])

            status, error = api.request(
                "POST",
                f"/api/exam-results/{result['id']}/external-results",
                {**payload, "version": result["version"], "points": "83"},
                credentials=self.chair,
            )

        assert_status(status, HTTPStatus.BAD_REQUEST)
        self.assertIn("Ersetzung", error["error"])

    def test_calculation_history_tracks_current_inputs_and_withdrawn_revisions(self) -> None:
        with ApiServer(self.db_path) as api:
            result = self.prepare_result(api)
            for actor, points in ((self.chair, "8"), (self.examiner, "8"), (self.deputy, "8")):
                for component, criterion in (
                    ("documentation", "quality"),
                    ("presentation", "delivery"),
                    ("discussion", "depth"),
                ):
                    result = self.save(api, result, actor, component, criterion, points)

            with session_scope(self.db_path) as session:
                chair_assessment_id = session.scalar(
                    select(IndividualAssessment.id).where(
                        IndividualAssessment.exam_result_id == result["id"],
                        IndividualAssessment.component_key == "documentation",
                        IndividualAssessment.assessor_member_id == 1,
                        IndividualAssessment.status == "submitted",
                    )
                )
            status, result = api.request(
                "POST",
                f"/api/exam-results/{result['id']}/individual-assessments/{chair_assessment_id}/withdraw",
                {"version": result["version"], "reason": "Beitrag wird neu erfasst"},
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)

            self.assertEqual("incomplete", result["state"])
            self.assertIsNone(result["current_calculation"])
            status, error = api.request(
                "POST",
                f"/api/exam-results/{result['id']}/determine",
                {
                    "version": result["version"],
                    "participant_member_ids": [1, 2, 3],
                    "vote": {"yes": [1, 2, 3], "no": [], "abstain": []},
                    "dissent": [],
                },
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.BAD_REQUEST)
            self.assertIn("berechnungsbereit", error["error"])

            result = self.save(
                api,
                result,
                self.chair,
                "documentation",
                "quality",
                "8",
                change_reason="Neuer Beitrag nach Rücknahme",
            )

            for component in ("documentation", "presentation", "discussion"):
                status, result = api.request(
                    "POST",
                    f"/api/exam-results/{result['id']}/disclosures",
                    {"version": result["version"], "component_key": component},
                    credentials=self.chair,
                )
                self.assertEqual(HTTPStatus.OK, status, result)
                if component != "documentation":
                    status, result = api.request(
                        "POST",
                        f"/api/exam-results/{result['id']}/committee-assessments",
                        {
                            "version": result["version"],
                            "component_key": component,
                            "points": "80",
                            "participant_member_ids": [1, 2, 3],
                            "vote": {"yes": [1, 2], "no": [3], "abstain": []},
                            "dissent": [],
                        },
                        credentials=self.chair,
                    )
                    self.assertEqual(HTTPStatus.OK, status, result)

            status, result = api.request(
                "POST",
                f"/api/exam-results/{result['id']}/external-results",
                {
                    "version": result["version"],
                    "area_key": "written",
                    "points": "82",
                    "grade": "gut",
                    "professional_status": "bestanden",
                    "determining_authority": "IHK Teststadt",
                    "source_reference": "Bescheid TEST-2026-0001",
                },
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            external_id = result["external_results"][-1]["id"]
            status, result = api.request(
                "POST",
                f"/api/exam-results/{result['id']}/external-results/{external_id}/confirm",
                {"version": result["version"]},
                credentials=self.deputy,
            )
            assert_status(status, HTTPStatus.OK)
            original_fingerprint = result["current_calculation"]["input_fingerprint"]

            result = self.save(
                api,
                result,
                self.chair,
                "documentation",
                "quality",
                "9",
                change_reason="Korrektur für Berechnungshistorie",
            )
            changed_fingerprint = result["current_calculation"]["input_fingerprint"]
            self.assertNotEqual(original_fingerprint, changed_fingerprint)
            result = self.save(
                api,
                result,
                self.chair,
                "documentation",
                "quality",
                "8",
                change_reason="Rückkehr zum vorherigen Berechnungsstand",
            )
            self.assertEqual(
                original_fingerprint, result["current_calculation"]["input_fingerprint"]
            )
            self.assertEqual(2, len(result["calculations"]))

            self.assertEqual("calculation_ready", result["state"])
            self.assertEqual(
                original_fingerprint, result["current_calculation"]["input_fingerprint"]
            )

            with session_scope(self.db_path) as session:
                chair_revisions = list(
                    session.scalars(
                        select(IndividualAssessment.revision)
                        .where(
                            IndividualAssessment.exam_result_id == result["id"],
                            IndividualAssessment.component_key == "documentation",
                            IndividualAssessment.assessor_member_id == 1,
                        )
                        .order_by(IndividualAssessment.revision)
                    )
                )
                examiner_revisions = list(
                    session.scalars(
                        select(IndividualAssessment.revision)
                        .where(
                            IndividualAssessment.exam_result_id == result["id"],
                            IndividualAssessment.component_key == "documentation",
                            IndividualAssessment.assessor_member_id == 2,
                        )
                        .order_by(IndividualAssessment.revision)
                    )
                )
            self.assertEqual([1, 2, 3, 4, 5], chair_revisions)
            self.assertEqual([1], examiner_revisions)

    def test_parallel_retention_changes_claim_one_result_version_atomically(self) -> None:
        with ApiServer(self.db_path) as api:
            result = self.prepare_result(api)

        context = SQLiteAuthenticationRepository(self.db_path).authenticate(self.chair.token)
        self.assertIsNotNone(context)
        scope = authorization_service(self.db_path).scope(context)
        actor = {
            "person_id": scope.person_id,
            "person_ids": tuple(scope.person_ids),
            "committee_ids": tuple(scope.committee_ids),
            "member_ids": tuple(scope.member_ids),
            "management_committee_ids": tuple(scope.management_committee_ids),
            "member_by_committee": dict(scope.member_by_committee),
        }
        initial_version = result["version"]
        with session_scope(self.db_path) as session:
            initial_day_revision = session.get(ExamDay, self.day_id).revision

        barrier = Barrier(2)

        def update_retention(retain_until: str) -> str:
            try:
                barrier.wait(timeout=10)
                exam_result_service(self.db_path).set_retention(
                    actor,
                    result["id"],
                    {
                        "version": initial_version,
                        "period_start": "2026-11-16",
                        "retain_until": retain_until,
                        "legal_hold": False,
                    },
                )
            except ExamResultConflictError:
                return "conflict"
            return "committed"

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(update_retention, ("2041-11-16", "2042-11-16")))

        self.assertCountEqual(["committed", "conflict"], outcomes)
        with session_scope(self.db_path) as session:
            stored_result = session.get(ExamResult, result["id"])
            retention = session.query(ResultRetention).filter_by(exam_result_id=result["id"]).one()
            day = session.get(ExamDay, self.day_id)
            final_version = stored_result.version
            final_retain_until = retention.retain_until
            final_day_revision = day.revision

        self.assertEqual(initial_version + 1, final_version)
        self.assertIn(final_retain_until, {"2041-11-16", "2042-11-16"})
        self.assertEqual(initial_day_revision + 1, final_day_revision)

    def test_calculation_history_and_exports_wait_for_component_disclosure(self) -> None:
        rules = assessment_rules()
        component = rules["components"][0]
        component["weight"] = "100"
        component["required_assessors"] = 2
        component["max_deviation"] = "100"
        component["additional_assessor_on_deviation"] = False
        rules["components"] = [component]
        rules["external_areas"] = []
        rules["passing"]["external_minima"] = {}

        with ApiServer(self.db_path) as api:
            result = self.prepare_result(api, rules=rules)
            result = self.save(api, result, self.chair, "documentation", "quality", "5")
            result = self.save(api, result, self.examiner, "documentation", "quality", "9")
            result = self.save(
                api,
                result,
                self.chair,
                "documentation",
                "quality",
                "6",
                change_reason="Korrektur vor Offenlegung",
            )
            result_id = result["id"]

            status, before = api.request(
                "GET", f"/api/exam-results/{result_id}", credentials=self.examiner
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual([], before["calculations"])
            self.assertIsNone(before["current_calculation"])

            status, machine_before = api.request(
                "GET",
                f"/api/exam-results/{result_id}/export.json",
                credentials=self.examiner,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual([], machine_before["result"]["calculations"])
            self.assertIsNone(machine_before["result"]["current_calculation"])

            status, _headers, human_before = api.request_raw(
                "GET",
                f"/api/exam-results/{result_id}/export.txt",
                credentials=self.examiner,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertNotIn("Berechnungsweg:", human_before.decode("utf-8"))
            self.assertNotIn("Gesamtergebnis:", human_before.decode("utf-8"))

            status, disclosed = api.request(
                "POST",
                f"/api/exam-results/{result_id}/disclosures",
                {
                    "version": before["version"],
                    "component_key": "documentation",
                },
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(
                ["70", "75"],
                [item["total_points"] for item in disclosed["calculations"]],
            )
            self.assertEqual("75", disclosed["current_calculation"]["total_points"])

            status, machine_after = api.request(
                "GET",
                f"/api/exam-results/{result_id}/export.json",
                credentials=self.examiner,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(
                ["70", "75"],
                [item["total_points"] for item in machine_after["result"]["calculations"]],
            )
            self.assertEqual("75", machine_after["result"]["current_calculation"]["total_points"])

            status, _headers, human_after = api.request_raw(
                "GET",
                f"/api/exam-results/{result_id}/export.txt",
                credentials=self.examiner,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertIn("Berechnungsweg:", human_after.decode("utf-8"))
            self.assertIn("Gesamtergebnis: 75 Punkte", human_after.decode("utf-8"))

    @staticmethod
    def save(
        api: ApiServer,
        result: dict,
        credentials,
        component: str,
        criterion: str,
        raw_points: str,
        **extra,
    ) -> dict:
        status, result = api.request(
            "POST",
            f"/api/exam-results/{result['id']}/individual-assessments",
            {
                "version": result["version"],
                "component_key": component,
                "criterion_key": criterion,
                "raw_points": raw_points,
                "submitted": True,
                **extra,
            },
            credentials=credentials,
        )
        assert_status(status, HTTPStatus.OK)
        return result

    def test_model_validation_binding_and_access_boundaries(self) -> None:
        invalid = assessment_rules()
        invalid["components"][0]["weight"] = "21"
        with ApiServer(self.db_path) as api:
            status, error = api.request(
                "POST",
                "/api/assessment-model-versions",
                self.model_payload(rules=invalid),
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.BAD_REQUEST)
            self.assertIn("100 Prozent", error["error"])

            invalid_bindings = (
                (90, "ihk", "IHK Fremdstadt", "zuständigen IHK"),
                (91, "occupation", "Kaufmann/-frau", "Ausbildungsberuf"),
                (92, "specialization", "application_development", "Schwerpunkten"),
                (93, "valid_from", "2027-01-01", "nicht gültig"),
            )
            for version, field, value, message in invalid_bindings:
                with self.subTest(applicability=field):
                    payload = self.model_payload(version=version)
                    payload[field] = value
                    if field == "valid_from":
                        payload["valid_until"] = "2027-12-31"
                    status, model = api.request(
                        "POST",
                        "/api/assessment-model-versions",
                        payload,
                        credentials=self.chair,
                    )
                    assert_status(status, HTTPStatus.CREATED)
                    status, error = api.request(
                        "POST",
                        "/api/exam-rounds/1/assessment-model-binding",
                        {
                            "assessment_model_version_id": model["id"],
                            "reason": "Negativer Gültigkeitstest",
                        },
                        credentials=self.chair,
                    )
                    assert_status(status, HTTPStatus.BAD_REQUEST)
                    self.assertIn(message, error["error"])

            result = self.prepare_result(api)
            status, draft_export = api.request(
                "GET",
                f"/api/exam-results/{result['id']}/export.json",
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("draft", draft_export["export_status"])
            self.assertFalse(draft_export["official_document"])
            status, exported_protocol = api.request(
                "GET",
                f"/api/exam-protocols/{self.protocol_id}/export.json",
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(
                {
                    "available": True,
                    "exam_result_id": result["id"],
                    "state": "incomplete",
                    "legacy_status": None,
                },
                exported_protocol["references"]["assessment"],
            )
            self.assertEqual({"min": "0", "max": "100"}, result["model_version"]["official_scale"])
            self.assertEqual("incomplete", result["state"])

            for credentials in (self.outsider, self.operator):
                status, _error = api.request(
                    "GET", f"/api/exam-results/{result['id']}", credentials=credentials
                )
                assert_status(status, HTTPStatus.FORBIDDEN)

            result = self.save(api, result, self.chair, "documentation", "quality", "8")
            status, hidden = api.request(
                "GET", f"/api/exam-results/{result['id']}", credentials=self.examiner
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual([], hidden["individual_assessments"])
            self.assertEqual(
                [{"component_key": "documentation", "draft": 0, "submitted": 1}],
                hidden["individual_assessment_counts"],
            )

            status, second_model = api.request(
                "POST",
                "/api/assessment-model-versions",
                self.model_payload(version=2),
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.CREATED)
            status, error = api.request(
                "POST",
                "/api/exam-rounds/1/assessment-model-binding",
                {
                    "assessment_model_version_id": second_model["id"],
                    "version": 1,
                    "reason": "Nicht mehr zulässiger Wechsel",
                },
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.CONFLICT)
            self.assertIn("ersten Bewertung", error["error"]["message"])

    def test_complete_result_lifecycle_with_correction_and_exports(self) -> None:
        with ApiServer(self.db_path) as api:
            result = self.prepare_result(api)
            credentials = ((self.chair, "10"), (self.examiner, "5"), (self.deputy, "8"))
            for actor, points in credentials:
                result = self.save(api, result, actor, "documentation", "quality", points)
                result = self.save(api, result, actor, "presentation", "delivery", points)
                result = self.save(api, result, actor, "discussion", "depth", points)
                if points == "5":
                    status, error = api.request(
                        "POST",
                        f"/api/exam-results/{result['id']}/disclosures",
                        {"version": result["version"], "component_key": "documentation"},
                        credentials=self.chair,
                    )
                    assert_status(status, HTTPStatus.BAD_REQUEST)
                    self.assertIn("individuellen Beiträge", error["error"])

            self.assertIsNone(result["current_calculation"])
            for component in ("documentation", "presentation", "discussion"):
                status, result = api.request(
                    "POST",
                    f"/api/exam-results/{result['id']}/disclosures",
                    {"version": result["version"], "component_key": component},
                    credentials=self.chair,
                )
                assert_status(status, HTTPStatus.OK)
                if component == "documentation":
                    self.assertEqual(5, len(result["individual_assessments"]))
                    continue

                if component == "presentation":
                    status, error = api.request(
                        "POST",
                        f"/api/exam-results/{result['id']}/committee-assessments",
                        {
                            "version": result["version"],
                            "component_key": component,
                            "points": "40",
                            "participant_member_ids": [1, 2, 3],
                            "vote": {"yes": [1, 2], "no": [3], "abstain": []},
                            "dissent": [],
                        },
                        credentials=self.chair,
                    )
                    assert_status(status, HTTPStatus.BAD_REQUEST)
                    self.assertIn("außerhalb der Einzelspanne", error["error"])

                status, result = api.request(
                    "POST",
                    f"/api/exam-results/{result['id']}/committee-assessments",
                    {
                        "version": result["version"],
                        "component_key": component,
                        "points": "75",
                        "participant_member_ids": [1, 2, 3],
                        "vote": {"yes": [1, 2], "no": [3], "abstain": []},
                        "dissent": [{"member_id": 3, "statement": "Abweichende Punktebewertung"}],
                    },
                    credentials=self.chair,
                )
                assert_status(status, HTTPStatus.OK)

            status, completion = api.request(
                "GET",
                f"/api/confirmed-plan-days/{self.day_id}/result-completion",
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertTrue(completion["closing_ready"])
            self.assertTrue(completion["slots"][0]["day_assessments_complete"])
            self.assertTrue(
                all(item["complete"] for item in completion["slots"][0]["day_assessments"])
            )
            self.assertEqual(["written"], completion["slots"][0]["external_inputs_pending"])

            status, result = api.request(
                "POST",
                f"/api/exam-results/{result['id']}/external-results",
                {
                    "version": result["version"],
                    "area_key": "written",
                    "points": "82",
                    "grade": "gut",
                    "professional_status": "bestanden",
                    "determining_authority": "IHK Teststadt",
                    "source_reference": "Bescheid TEST-2026-0001",
                },
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            external_id = result["external_results"][-1]["id"]
            self.assertIsNone(result["current_calculation"])

            status, _error = api.request(
                "POST",
                f"/api/exam-results/{result['id']}/external-results/{external_id}/confirm",
                {"version": result["version"]},
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.FORBIDDEN)
            confirmation_request = {"version": result["version"]}
            status, result = api.request(
                "POST",
                f"/api/exam-results/{result['id']}/external-results/{external_id}/confirm",
                confirmation_request,
                credentials=self.deputy,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("calculation_ready", result["state"])
            self.assertEqual("79", result["current_calculation"]["total_points"])
            self.assertTrue(result["current_calculation"]["passed"])
            confirmed_version = result["version"]
            status, retried = api.request(
                "POST",
                f"/api/exam-results/{result['id']}/external-results/{external_id}/confirm",
                confirmation_request,
                credentials=self.deputy,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(confirmed_version, retried["version"])

            status, result = api.request(
                "POST",
                f"/api/exam-results/{result['id']}/external-results",
                {
                    "version": result["version"],
                    "area_key": "written",
                    "points": "84",
                    "grade": "gut",
                    "professional_status": "bestanden",
                    "determining_authority": "IHK Teststadt",
                    "source_reference": "Berichtigter Bescheid TEST-2026-0001",
                    "correction_reason": "Übertragungsfehler der Quelle berichtigt",
                },
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("replaced", result["external_results"][0]["status"])
            self.assertEqual("unconfirmed", result["external_results"][1]["status"])
            self.assertIsNone(result["current_calculation"])
            corrected_external_id = result["external_results"][1]["id"]
            status, result = api.request(
                "POST",
                f"/api/exam-results/{result['id']}/external-results/{corrected_external_id}/confirm",
                {"version": result["version"]},
                credentials=self.deputy,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("80", result["current_calculation"]["total_points"])
            status, completion = api.request(
                "GET",
                f"/api/confirmed-plan-days/{self.day_id}/result-completion",
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertFalse(completion["closing_ready"])
            self.assertTrue(completion["slots"][0]["overall_determination_pending"])

            status, error = api.request(
                "POST",
                f"/api/exam-results/{result['id']}/determine",
                {
                    "version": result["version"],
                    "participant_member_ids": [1, 2],
                    "vote": {"yes": [1, 2], "no": [], "abstain": []},
                    "dissent": [],
                },
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.BAD_REQUEST)
            self.assertIn("ordnungsgemäß besetzt", error["error"])

            status, result = api.request(
                "POST",
                f"/api/exam-results/{result['id']}/determine",
                {
                    "version": result["version"],
                    "participant_member_ids": [1, 2, 3],
                    "vote": {"yes": [1, 2], "no": [3], "abstain": []},
                    "dissent": [{"member_id": 3, "statement": "Abweichendes Gesamtergebnis"}],
                },
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("determined", result["state"])
            determination = result["determinations"][0]
            self.assertIn("result_calculation_id", determination)
            self.assertNotIn("calculation_id", determination)
            with session_scope(self.db_path) as session:
                external = session.get(ExternalExamResult, corrected_external_id)
                external.status = "unconfirmed"
                external.confirmed_by_member_id = None
                external.confirmed_at = None
            status, _error = api.request(
                "POST",
                f"/api/exam-results/{result['id']}/external-results/{corrected_external_id}/confirm",
                {"version": result["version"]},
                credentials=self.deputy,
            )
            assert_status(status, HTTPStatus.CONFLICT)
            with session_scope(self.db_path) as session:
                external = session.get(ExternalExamResult, corrected_external_id)
                external.status = "confirmed"
                external.confirmed_by_member_id = 3
                external.confirmed_at = "2026-11-16T10:00:00+01:00"
            status, updated = api.request(
                "GET", f"/api/exam-results/{result['id']}", credentials=self.chair
            )
            assert_status(status, HTTPStatus.OK)
            result = updated
            determined_version = result["version"]
            status, repeated = api.request(
                "POST",
                f"/api/exam-results/{result['id']}/determine",
                {
                    "version": determined_version - 1,
                    "participant_member_ids": [1, 2, 3],
                    "vote": {"yes": [1, 2], "no": [3], "abstain": []},
                    "dissent": [{"member_id": 3, "statement": "Abweichendes Gesamtergebnis"}],
                },
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(determined_version, repeated["version"])
            self.assertEqual(1, len(repeated["determinations"]))
            result = repeated
            status, completion = api.request(
                "GET",
                f"/api/confirmed-plan-days/{self.day_id}/result-completion",
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertFalse(completion["closing_ready"])
            self.assertFalse(completion["slots"][0]["record_confirmations_complete"])

            for actor in (self.chair, self.deputy, self.examiner):
                status, result = api.request(
                    "POST",
                    f"/api/exam-results/{result['id']}/record-confirmations",
                    {"version": result["version"]},
                    credentials=actor,
                )
                assert_status(status, HTTPStatus.OK)

            status, completion = api.request(
                "GET",
                f"/api/confirmed-plan-days/{self.day_id}/result-completion",
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertTrue(completion["closing_ready"])
            self.assertTrue(completion["slots"][0]["record_confirmations_complete"])

            status, result = api.request(
                "POST",
                f"/api/exam-results/{result['id']}/communications",
                {
                    "version": result["version"],
                    "method": "persönliche Bekanntgabe",
                    "communicated_at": "2026-11-16T10:30:00+01:00",
                    "external_document_status": "ausstehend",
                    "external_document_reference": "IHK-Fachverfahren",
                },
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("communicated", result["state"])

            status, exported = api.request(
                "GET", f"/api/exam-results/{result['id']}/export.json", credentials=self.chair
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(result["id"], exported["result"]["id"])
            exported_determination = exported["result"]["current_determination"]
            self.assertIn("result_calculation_id", exported_determination)
            self.assertNotIn("calculation_id", exported_determination)
            status, headers, body = api.request_raw(
                "GET", f"/api/exam-results/{result['id']}/export.txt", credentials=self.chair
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("text/plain; charset=utf-8", headers["content-type"])
            self.assertIn("Ergebnisniederschrift", body.decode("utf-8"))

            status, completion = api.request(
                "GET",
                f"/api/confirmed-plan-days/{self.day_id}/result-completion",
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertTrue(completion["closing_ready"])

            status, result = api.request(
                "POST",
                f"/api/exam-results/{result['id']}/corrections",
                {"version": result["version"], "reason": "Übertragungsfehler in Rohpunkten"},
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertTrue(result["correction_open"])
            result = self.save(
                api,
                result,
                self.chair,
                "documentation",
                "quality",
                "9",
                change_reason="Übertragungsfehler berichtigt",
            )
            status, result = api.request(
                "POST",
                f"/api/exam-results/{result['id']}/determine",
                {
                    "version": result["version"],
                    "participant_member_ids": [1, 2, 3],
                    "vote": {"yes": [1, 2, 3], "no": [], "abstain": []},
                    "dissent": [],
                },
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertFalse(result["correction_open"])
            self.assertEqual(2, len(result["determinations"]))
            self.assertEqual("superseded", result["determinations"][0]["status"])
            self.assertEqual("obsolete", result["communications"][0]["status"])
            self.assertEqual("completed", result["corrections"][0]["status"])
            self.assertIn("result_determination_id", result["corrections"][0])
            self.assertNotIn("determination_id", result["corrections"][0])
            self.assertIn("result_determination_id", result["communications"][0])
            self.assertNotIn("determination_id", result["communications"][0])
            self.assertIn("result_determination_id", result["exports"][0])
            self.assertNotIn("determination_id", result["exports"][0])
            self.assertEqual(
                {"superseded"},
                {item["status"] for item in result["exports"]},
            )

            status, result = api.request(
                "PUT",
                f"/api/exam-results/{result['id']}/retention",
                {
                    "version": result["version"],
                    "period_start": "2026-11-16",
                    "retain_until": "2041-11-16",
                    "legal_hold": True,
                    "hold_reason": "Laufendes Rechtsbehelfsverfahren",
                },
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertNotIn("version", result["retention"])
            retained_version = result["version"]
            status, repeated = api.request(
                "PUT",
                f"/api/exam-results/{result['id']}/retention",
                {
                    "version": retained_version - 1,
                    "period_start": "2026-11-16",
                    "retain_until": "2041-11-16",
                    "legal_hold": True,
                    "hold_reason": "Laufendes Rechtsbehelfsverfahren",
                },
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(retained_version, repeated["version"])
            result = repeated

            status, error = api.request(
                "PUT",
                f"/api/exam-results/{result['id']}/retention",
                {
                    "version": result["version"],
                    "period_start": "2026-11-16",
                    "retain_until": "2030-12-31",
                    "legal_hold": True,
                    "hold_reason": "Laufendes Rechtsbehelfsverfahren",
                },
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.BAD_REQUEST)
            self.assertIn("Mindestaufbewahrung", error["error"])

            status, error = api.request(
                "PUT",
                f"/api/exam-results/{result['id']}/retention",
                {
                    "version": result["version"],
                    "period_start": "2026-11-16",
                    "retain_until": "2041-11-16",
                    "legal_hold": False,
                },
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.BAD_REQUEST)
            self.assertIn("Aufheben einer Sperre", error["error"])

            status, result = api.request(
                "PUT",
                f"/api/exam-results/{result['id']}/retention",
                {
                    "version": result["version"],
                    "period_start": "2026-11-16",
                    "retain_until": "2041-11-16",
                    "legal_hold": False,
                    "release_reason": "Rechtsbehelfsverfahren abgeschlossen",
                },
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertFalse(result["retention"]["legal_hold"])
            self.assertEqual(
                "Freigabe: Rechtsbehelfsverfahren abgeschlossen",
                result["retention"]["hold_reason"],
            )


if __name__ == "__main__":
    unittest.main()
