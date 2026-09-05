"""Legacy fixture helpers kept for focused backend scenario tests.

The public-demo artifact is compiled from the profile SQL and never calls these
helpers.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from .synthetic_fixtures_generated import (
    FIXTURE_IDS,
    FIXTURE_ROOT,
    ORGANIZATION_NAMES,
)


def _fixture_id(suffix: str) -> int:
    return int(FIXTURE_IDS[f"{FIXTURE_ROOT}.{suffix}"]["id"])


def _add_exam_protocol_scenario(database: Path) -> None:
    """Add one started synthetic exam without changing the general development seed."""
    assessment_rules = {
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
                        "key": "professional_quality",
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
                "key": "technical_discussion",
                "label": "Fachgespräch",
                "mode": "committee",
                "weight": "15",
                "day_scoped": True,
                "required_assessors": 3,
                "max_deviation": "15",
                "additional_assessor_on_deviation": False,
                "criteria": [
                    {
                        "key": "professional_depth",
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
                "key": "written_exam",
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
            "external_minima": {},
        },
        "quorum": {"minimum_members": 3, "majority": "simple"},
    }
    with closing(sqlite3.connect(database)) as connection:
        connection.executescript("""
            INSERT INTO exam_half_year (id, season, year, status)
            VALUES (2, 'summer', 2027, 'active');

            INSERT INTO exam_round
              (id, exam_half_year_id, committee_id, name, status, created_by_member_id)
            VALUES
              (2, 2, 1, 'Sommer 2027 – Protokolldemo', 'plan_confirmed', 1);

            INSERT INTO round_candidate
              (id, exam_round_id, candidate_id, attempt_number, requires_mep)
            VALUES (13, 2, 1, 1, 0);

            INSERT INTO candidate_committee_assignment
              (candidate_id, exam_half_year_id, exam_round_id, round_candidate_id)
            VALUES (1, 2, 2, 13);

            INSERT INTO exam_day
              (id, exam_round_id, room_id, date, status, lunch_break_enabled,
               created_from_proposal)
            VALUES (1, 2, 1, '2027-05-18', 'confirmed', 1, 1);

            INSERT INTO exam_slot
              (id, exam_day_id, round_candidate_id, slot_type, starts_at, ends_at,
               sequence_number, status, actual_started_at, execution_status,
               status_changed_at)
            VALUES
              (1, 1, 13, 'regular', '2027-05-18 09:00:00', '2027-05-18 10:00:00',
               1, 'confirmed', '2027-05-18 09:03:00', 'running',
               '2027-05-18 09:03:00');

            INSERT INTO exam_day_assignment
              (id, exam_day_id, committee_member_id, assignment_role, day_part)
            VALUES
              (1, 1, 1, 'examiner', 'full_day'),
              (2, 1, 2, 'examiner', 'full_day'),
              (3, 1, 3, 'examiner', 'full_day');

            INSERT INTO candidate_exam_attendance
              (exam_slot_id, status, arrived_at)
            VALUES (1, 'present', '2027-05-18 08:55:00');

            INSERT INTO member_exam_attendance
              (exam_day_id, committee_member_id, status, arrived_at)
            VALUES
              (1, 1, 'present', '2027-05-18 08:45:00'),
              (1, 2, 'present', '2027-05-18 08:47:00'),
              (1, 3, 'present', '2027-05-18 08:50:00');

            INSERT INTO exam_protocol
              (id, exam_slot_id, current_version, created_by_member_id, source,
               created_at, updated_at)
            VALUES
              (1, 1, 1, 1, 'application', '2027-05-18 09:03:00',
               '2027-05-18 09:03:00');

            INSERT INTO exam_protocol_participant
              (exam_protocol_id, committee_member_id, created_at)
            VALUES
              (1, 1, '2027-05-18 09:03:00'),
              (1, 2, '2027-05-18 09:03:00'),
              (1, 3, '2027-05-18 09:03:00');

            INSERT INTO exam_protocol_revision
              (id, exam_protocol_id, version, workflow_state, changed_by_member_id,
               change_reason, created_at)
            VALUES
              (1, 1, 1, 'draft', 1, 'exam_started', '2027-05-18 09:03:00');
        """)
        connection.execute(
            """
            INSERT INTO assessment_model_version
              (id, model_key, version, ihk, occupation, specialization,
               training_regulation, exam_regulation, ihk_guidelines, valid_from,
               valid_until, official_scale_min, official_scale_max, rules_json,
               retention_rule_reference, retention_years, created_by_member_id, created_at)
            VALUES
              (1, 'demo-fisi-2027', 1, ?, 'Fachinformatiker/in', NULL,
               'Synthetische Ausbildungsordnung Athen 2020',
               'Synthetische Prüfungsordnung Athen 2027',
               'Verbindliche Demo-Richtlinie Athen 2027', '2027-01-01', '2027-12-31',
               '0', '100', ?, 'Demo-PrüfO Athen § 31', 15, 1,
               '2027-01-01 00:00:00')
            """,
            (
                ORGANIZATION_NAMES[f"{FIXTURE_ROOT}.organization.athen"],
                json.dumps(assessment_rules, ensure_ascii=False, sort_keys=True),
            ),
        )
        connection.executescript("""
            INSERT INTO exam_round_assessment_binding
              (id, exam_round_id, assessment_model_version_id, version,
               bound_by_member_id, binding_reason, bound_at)
            VALUES
              (1, 2, 1, 1, 1, 'Synthetischer Demo-Ergebnisprozess',
               '2027-05-18 08:00:00');

            INSERT INTO exam_result
              (id, round_candidate_id, current_state, correction_open, version,
               source, created_at, updated_at)
            VALUES
              (1, 13, 'incomplete', 0, 1, 'application',
               '2027-05-18 09:03:00', '2027-05-18 09:03:00');

            INSERT INTO round_candidate
              (id, exam_round_id, candidate_id, attempt_number, requires_mep)
            VALUES
              (14, 2, 2, 1, 0),
              (15, 2, 3, 1, 0);

            INSERT INTO candidate_committee_assignment
              (candidate_id, exam_half_year_id, exam_round_id, round_candidate_id)
            VALUES
              (2, 2, 2, 14),
              (3, 2, 2, 15);

            INSERT INTO exam_day
              (id, exam_round_id, room_id, date, status, lunch_break_enabled,
               created_from_proposal)
            VALUES
              (2, 2, 1, '2027-05-19', 'confirmed', 1, 1),
              (3, 2, 1, '2027-05-20', 'confirmed', 1, 1);

            INSERT INTO exam_slot
              (id, exam_day_id, round_candidate_id, slot_type, starts_at, ends_at,
               sequence_number, status, actual_started_at, execution_status,
               status_changed_at, actual_completed_at, status_reason)
            VALUES
              (2, 2, 14, 'regular', '2027-05-19 09:00:00', '2027-05-19 10:00:00',
               1, 'confirmed', NULL, 'cancelled', '2027-05-19 08:30:00', NULL,
               'Synthetischer begründeter Prüfungsausfall'),
              (3, 3, 15, 'regular', '2027-05-20 09:00:00', '2027-05-20 10:00:00',
               1, 'confirmed', '2027-05-20 09:02:00', 'completed',
               '2027-05-20 10:00:00', '2027-05-20 09:58:00', NULL);

            INSERT INTO exam_day_assignment
              (id, exam_day_id, committee_member_id, assignment_role, day_part)
            VALUES
              (4, 3, 1, 'examiner', 'full_day'),
              (5, 3, 2, 'examiner', 'full_day'),
              (6, 3, 3, 'examiner', 'full_day');

            INSERT INTO candidate_exam_attendance
              (exam_slot_id, status, arrived_at)
            VALUES (3, 'present', '2027-05-20 08:55:00');

            INSERT INTO member_exam_attendance
              (exam_day_id, committee_member_id, status, arrived_at)
            VALUES
              (3, 1, 'present', '2027-05-20 08:45:00'),
              (3, 2, 'present', '2027-05-20 08:47:00'),
              (3, 3, 'present', '2027-05-20 08:50:00');

            INSERT INTO exam_protocol
              (id, exam_slot_id, current_version, created_by_member_id, source,
               created_at, updated_at)
            VALUES
              (2, 3, 1, 1, 'application', '2027-05-20 09:02:00',
               '2027-05-20 10:02:00');

            INSERT INTO exam_protocol_participant
              (exam_protocol_id, committee_member_id, created_at)
            VALUES
              (2, 1, '2027-05-20 09:02:00'),
              (2, 2, '2027-05-20 09:02:00'),
              (2, 3, '2027-05-20 09:02:00');

            INSERT INTO exam_protocol_revision
              (id, exam_protocol_id, version, declaration, workflow_state,
               changed_by_member_id, submitted_by_member_id, submitted_at, created_at)
            VALUES
              (2, 2, 1, 'without_special_occurrences', 'submitted', 1, 1,
               '2027-05-20 10:02:00', '2027-05-20 09:02:00');

            INSERT INTO exam_protocol_response
              (exam_protocol_revision_id, committee_member_id, response, responded_at)
            VALUES
              (2, 1, 'confirmed', '2027-05-20 10:03:00'),
              (2, 2, 'confirmed', '2027-05-20 10:04:00');

            INSERT INTO exam_result
              (id, round_candidate_id, current_state, correction_open, version,
               source, created_at, updated_at)
            VALUES
              (2, 15, 'incomplete', 0, 1, 'application',
               '2027-05-20 09:02:00', '2027-05-20 10:04:00');

            INSERT INTO individual_assessment
              (id, exam_result_id, component_key, criterion_key, assessor_member_id,
               revision, raw_points, normalized_points, status, submitted_at)
            VALUES
              (1, 2, 'documentation', 'professional_quality', 1, 1, '8', '80',
               'submitted', '2027-05-20 09:55:00'),
              (2, 2, 'documentation', 'professional_quality', 2, 1, '8', '80',
               'submitted', '2027-05-20 09:56:00');

            INSERT INTO committee_assessment
              (id, exam_result_id, component_key, revision, points,
               participant_member_ids_json, vote_json, dissent_json, status,
               determined_by_member_id, determined_at)
            VALUES
              (1, 2, 'presentation', 1, '80', '[1,2,3]',
               '{"yes":[1,2,3],"no":[],"abstain":[]}', '[]', 'current', 1,
               '2027-05-20 09:57:00'),
              (2, 2, 'technical_discussion', 1, '80', '[1,2,3]',
               '{"yes":[1,2,3],"no":[],"abstain":[]}', '[]', 'current', 1,
               '2027-05-20 09:58:00');
        """)
        connection.commit()


def _add_exam_round_lifecycle_scenarios(database: Path) -> None:
    """Add isolated positive and negative round-lifecycle demo states."""
    foreign_committee_id = _fixture_id("committee.feenwald")
    foreign_chair_id = _fixture_id("membership.chair.feenwald")
    with closing(sqlite3.connect(database)) as connection:
        connection.executescript(f"""
            INSERT INTO exam_half_year (id, season, year, status) VALUES
              (90, 'summer', 2028, 'active'),
              (91, 'winter', 2028, 'active'),
              (92, 'summer', 2029, 'active'),
              (93, 'winter', 2029, 'active');

            INSERT INTO exam_round (
              id, exam_half_year_id, committee_id, name, status, plan_revision,
              revision, lifecycle_status, created_by_member_id
            ) VALUES
              (90, 90, 1, 'Sommer 2028 · leere Entwurfsrunde', 'draft', 0, 1, 'open', 1),
              (91, 91, 1, 'Winter 2028 · absagbare Runde', 'draft', 0, 1, 'open', 1),
              (92, 92, 1, 'Sommer 2029 · abschließbare Runde', 'plan_confirmed', 1, 1, 'open', 1),
              (93, 93, 1, 'Winter 2029 · abgeschlossene Runde',
               'plan_confirmed', 1, 2, 'closed', 1),
              (94, 92, {foreign_committee_id}, 'Sommer 2029 · Fremdrunde Feenwald',
               'draft', 0, 1, 'open', {foreign_chair_id});

            INSERT INTO round_candidate (
              id, exam_round_id, candidate_id, attempt_number, requires_mep, is_active,
              terminal_status, terminal_reason, postponed_until, terminal_at
            ) VALUES
              (90, 91, 1, 1, 0, 0, 'postponed', 'Synthetische Neuplanung',
               '2029-05-01', '2026-01-01T00:00:00+00:00'),
              (91, 92, 2, 1, 0, 0, 'postponed', 'Synthetische Neuplanung',
               '2030-05-01', '2026-01-01T00:00:00+00:00'),
              (92, 93, 3, 1, 0, 0, 'postponed', 'Synthetische Neuplanung',
               '2030-11-01', '2026-01-01T00:00:00+00:00');

            INSERT INTO candidate_committee_assignment (
              id, candidate_id, exam_half_year_id, exam_round_id, round_candidate_id,
              assigned_at, ended_at
            ) VALUES
              (90, 1, 91, 91, 90, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'),
              (91, 2, 92, 92, 91, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'),
              (92, 3, 93, 93, 92, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');

            INSERT INTO exam_day (
              id, exam_round_id, room_id, date, status, revision, closure_status
            ) VALUES
              (90, 92, 1, '2029-05-15', 'completed', 2, 'closed'),
              (91, 93, 1, '2029-11-15', 'completed', 2, 'closed');

            INSERT INTO exam_day_closure (
              id, exam_day_id, requested_revision, resulting_revision, closure_type,
              actor_member_id, checklist_json, warnings_json, protocol_references_json,
              result_references_json, status, command_fingerprint, closed_at
            ) VALUES
              (90, 90, 1, 2, 'regular', 1, '[]', '[]', '[]', '[]', 'current',
               'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
               '2026-01-01T00:00:00+00:00'),
              (91, 91, 1, 2, 'regular', 1, '[]', '[]', '[]', '[]', 'current',
               'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
               '2026-01-01T00:00:00+00:00');

            INSERT INTO exam_round_decision (
              id, exam_round_id, decision_type, requested_revision, resulting_revision,
              actor_member_id, checklist_json, snapshot_json, status, command_fingerprint,
              decided_at
            ) VALUES (
              90, 93, 'close', 1, 2, 1, '[]', '{{"demo":"synthetic closed round"}}',
              'current',
              'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
              '2026-01-01T00:00:00+00:00'
            );
            INSERT INTO exam_round_audit_event (
              id, exam_round_id, round_revision, event_type, actor_member_id,
              decision_id, scope_json, created_at
            ) VALUES (
              90, 93, 2, 'closed', 1, 90, '[]', '2026-01-01T00:00:00+00:00'
            );
            INSERT INTO exam_round_export (
              id, exam_round_id, decision_id, round_revision, export_kind,
              lifecycle_status, generated_by_member_id, generated_at
            ) VALUES (
              90, 93, 90, 2, 'machine', 'closed', 1,
              '2026-01-01T00:00:00+00:00'
            );
        """)
        connection.commit()
