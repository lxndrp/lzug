from __future__ import annotations

import unittest
from decimal import Decimal
from http import HTTPStatus

from backend.auth import AuthenticationRepository
from backend.database import session_scope
from backend.exam_protocols import create_protocol_for_started_slot
from backend.exam_results import ExamResultService
from backend.models import (
    CandidateExamAttendance,
    ExamDay,
    ExamDayAssignment,
    ExamRound,
    ExamSlot,
    MemberExamAttendance,
)
from backend.tests.helpers import ApiServer, TempDatabase, assert_status
from demo.synthetic_fixtures_generated import FIXTURE_ROOT, ORGANIZATION_NAMES


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


class ExamResultTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = TempDatabase()
        self.db_path = self.database.__enter__()
        authentication = AuthenticationRepository(self.db_path)
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
                location_id=1,
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
            protocol = create_protocol_for_started_slot(
                session,
                slot_id=slot.id,
                participant_member_ids={1, 2, 3},
                created_by_member_id=1,
                created_at="2026-11-16T09:03:00+01:00",
            )
            self.day_id = day.id
            self.slot_id = slot.id
            self.protocol_id = protocol.id

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

    def prepare_result(self, api: ApiServer) -> dict:
        status, model = api.request(
            "POST", "/api/assessment-model-versions", self.model_payload(), credentials=self.chair
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
            status, result = api.request(
                "POST",
                f"/api/exam-results/{result['id']}/external-results/{external_id}/confirm",
                {"version": result["version"]},
                credentials=self.deputy,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("calculation_ready", result["state"])
            self.assertEqual("79", result["current_calculation"]["total_points"])
            self.assertTrue(result["current_calculation"]["passed"])

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
