from __future__ import annotations

import unittest

from backend.presentation.exam_exports import (
    render_day_closure_export,
    render_protocol_export,
    render_result_export,
    render_round_lifecycle_export,
)


class ExamExportRendererTests(unittest.TestCase):
    def test_result_renderer_preserves_draft_empty_and_determined_sections(self) -> None:
        result = {
            "id": 7,
            "state": "communicated",
            "model_version": {"model_key": "ihk", "version": 3},
            "candidate": {"first_name": "Ada", "last_name": "Lovelace", "ihk_exam_number": "A-7"},
            "external_results": [],
            "committee_assessments": [
                {"component_key": "oral", "points": "80", "status": "current"}
            ],
            "current_calculation": {
                "path": {
                    "inputs": [
                        {"kind": "component", "key": "oral", "points": "80", "weight": "100"}
                    ]
                },
                "total_points": "80",
                "grade": "gut",
                "passed": True,
            },
            "current_determination": {
                "revision": 2,
                "determined_at": "2026-11-16T12:00:00+00:00",
                "participant_member_ids": [1, 2],
                "confirmation_member_ids": [1, 2],
                "dissent": {"member": 3},
            },
            "correction_open": True,
            "communications": [
                {
                    "status": "current",
                    "communicated_at": "2026-11-16T13:00:00+00:00",
                    "method": "email",
                }
            ],
        }

        text = render_result_export(result)

        self.assertIn("Ergebnisniederschrift 7 – FESTGESTELLT", text)
        self.assertIn("- keine", text)
        self.assertIn("Gesamtergebnis: 80 Punkte, gut, bestanden", text)
        self.assertIn("Abweichende Voten: {'member': 3}", text)
        self.assertIn("Ergebnismitteilung: 2026-11-16T13:00:00+00:00 (email)", text)

    def test_protocol_renderer_preserves_incomplete_missing_completion_and_empty_responses(
        self,
    ) -> None:
        protocol = {
            "id": 8,
            "state": "draft",
            "closing_ready": False,
            "current_revision": {"declaration": None, "entries": [], "responses": []},
            "open_correction": False,
        }
        references = {
            "candidate": {"first_name": "Grace", "last_name": "Hopper", "ihk_exam_number": "G-8"},
            "slot": {
                "starts_at": "2026-11-16T09:00:00+01:00",
                "ends_at": "2026-11-16T10:00:00+01:00",
                "actual_started_at": "2026-11-16T09:01:00+01:00",
                "actual_completed_at": None,
            },
            "location": {"name": "Berlin", "room": "1"},
            "participants": [
                {
                    "first_name": "Katherine",
                    "last_name": "Johnson",
                    "attendance": {"status": "present"},
                }
            ],
        }

        text = render_protocol_export(protocol, references)

        self.assertIn("Prüfungsprotokoll 8 – UNVOLLSTÄNDIG", text)
        self.assertIn("Tatsächlicher Abschluss: nicht erfasst", text)
        self.assertIn("Verlauf: noch nicht festgestellt", text)
        self.assertIn("Reaktionen:\n- keine", text)

    def test_day_and_round_renderers_preserve_failed_checks_and_empty_collections(self) -> None:
        day_text = render_day_closure_export(
            {"id": 2, "date": "2026-11-16"},
            {
                "status": "closed_exception",
                "revision": 4,
                "evaluation": {"items": [{"ok": False, "label": "Protokoll fehlt"}]},
                "history": [],
            },
        )
        round_text = render_round_lifecycle_export(
            3,
            {
                "status": "cancelled",
                "revision": 5,
                "history": [],
                "retention": {"retain_until": None, "legal_hold": False},
                "ihk_statuses": [],
            },
            {
                "round": {"name": "Winterrunde"},
                "half_year": {"season": "Winter", "year": 2026},
                "committee": {"name": "Ausschuss A"},
                "candidates": [],
                "roles": [],
                "days": [],
                "results": [],
            },
        )

        self.assertIn("- nicht erfüllt: Protokoll fehlt", day_text)
        self.assertIn("Prüfungsrundennachweis 3", round_text)
        self.assertIn("- bis: nicht festgelegt", round_text)
        self.assertIn("- Sperre: nein", round_text)


if __name__ == "__main__":
    unittest.main()
