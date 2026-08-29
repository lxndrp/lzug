"""Version-bound assessments, calculations, determinations, and result records."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .authorization import AuthorizationScope
from .database import DEFAULT_DB_PATH, session_scope
from .exam_day_closures import (
    DayMutationGuard,
    complete_day_mutation,
    days_for_result,
    guard_day_mutation,
)
from .models import (
    AssessmentDisclosure,
    AssessmentModelVersion,
    Candidate,
    Committee,
    CommitteeAssessment,
    ExamDay,
    ExamDayReopening,
    ExamProtocol,
    ExamProtocolParticipant,
    ExamResult,
    ExamRound,
    ExamRoundAssessmentBinding,
    ExamSlot,
    ExternalExamResult,
    IndividualAssessment,
    ResultCalculation,
    ResultCommunication,
    ResultCorrection,
    ResultDetermination,
    ResultExport,
    ResultRecordConfirmation,
    ResultRetention,
    RoundCandidate,
)

MODEL_FIELDS = {
    "model_key",
    "version",
    "ihk",
    "occupation",
    "specialization",
    "training_regulation",
    "exam_regulation",
    "ihk_guidelines",
    "valid_from",
    "valid_until",
    "official_scale_min",
    "official_scale_max",
    "rules",
    "retention_rule_reference",
    "retention_years",
}
COMPONENT_FIELDS = {
    "key",
    "label",
    "mode",
    "weight",
    "day_scoped",
    "required_assessors",
    "max_deviation",
    "additional_assessor_on_deviation",
    "criteria",
}
CRITERION_FIELDS = {"key", "label", "raw_min", "raw_max", "weight"}
EXTERNAL_AREA_FIELDS = {"key", "label", "weight", "required"}
MODEL_MODES = {"committee", "independent"}
RESULT_STATES = {"incomplete", "calculation_ready", "determined", "communicated"}
HISTORY_STATUSES = {"current", "superseded"}


class ExamResultConflictError(ValueError):
    """Signal stale writes or repeated actions with different content."""


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _decimal_text(value: Decimal) -> str:
    normalized = format(value, "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


class ExamResultService:
    """Enforce the complete assessment and result lifecycle as one aggregate."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path

    # Assessment model and binding -------------------------------------------------

    def list_models(self, scope: AuthorizationScope) -> dict[str, Any]:
        if not scope.has_active_membership:
            raise PermissionError("Forbidden.")
        with session_scope(self.db_path) as session:
            models = list(
                session.scalars(
                    select(AssessmentModelVersion).order_by(
                        AssessmentModelVersion.model_key, AssessmentModelVersion.version
                    )
                )
            )
            return {"items": [self._model_view(item) for item in models]}

    def create_model(self, scope: AuthorizationScope, payload: dict[str, Any]) -> dict[str, Any]:
        if not scope.management_committee_ids:
            raise PermissionError("Forbidden.")
        if set(payload) - MODEL_FIELDS:
            raise ValueError("Die Bewertungsmodellversion enthält unzulässige Felder")
        rules = self._validate_rules(payload.get("rules"))
        official_min = self._decimal(payload.get("official_scale_min", 0), "official_scale_min")
        official_max = self._decimal(payload.get("official_scale_max", 100), "official_scale_max")
        if official_min != 0 or official_max != 100:
            raise ValueError(
                "Der aktuelle IHK-Ausbildungsprüfungsbereich verwendet 0 bis 100 Punkte"
            )
        valid_from = self._required_date(payload.get("valid_from"), "valid_from")
        valid_until = self._optional_date(payload.get("valid_until"), "valid_until")
        if valid_until is not None and valid_until < valid_from:
            raise ValueError("Der Gültigkeitszeitraum ist widersprüchlich")
        retention_years = self._integer(payload.get("retention_years", 15), "retention_years", 15)
        member_id = min(scope.member_ids)
        with session_scope(self.db_path) as session:
            model = AssessmentModelVersion(
                model_key=self._required_text(payload.get("model_key"), "model_key", 100),
                version=self._integer(payload.get("version"), "version", 1),
                ihk=self._required_text(payload.get("ihk"), "ihk", 300),
                occupation=self._required_text(payload.get("occupation"), "occupation", 300),
                specialization=self._optional_text(payload.get("specialization"), 300),
                training_regulation=self._required_text(
                    payload.get("training_regulation"), "training_regulation", 1000
                ),
                exam_regulation=self._required_text(
                    payload.get("exam_regulation"), "exam_regulation", 1000
                ),
                ihk_guidelines=self._required_text(
                    payload.get("ihk_guidelines"), "ihk_guidelines", 2000
                ),
                valid_from=valid_from.isoformat(),
                valid_until=valid_until.isoformat() if valid_until else None,
                official_scale_min=_decimal_text(official_min),
                official_scale_max=_decimal_text(official_max),
                rules_json=self._json(rules),
                retention_rule_reference=self._required_text(
                    payload.get("retention_rule_reference"),
                    "retention_rule_reference",
                    1000,
                ),
                retention_years=retention_years,
                created_by_member_id=member_id,
                created_at=_now(),
            )
            session.add(model)
            session.flush()
            return self._model_view(model)

    def get_round_binding(self, scope: AuthorizationScope, round_id: int) -> dict[str, Any] | None:
        with session_scope(self.db_path) as session:
            exam_round = session.get(ExamRound, round_id)
            if exam_round is None:
                return None
            if not scope.can_read_committee(exam_round.committee_id):
                raise PermissionError("Forbidden.")
            binding = session.scalar(
                select(ExamRoundAssessmentBinding).where(
                    ExamRoundAssessmentBinding.exam_round_id == round_id
                )
            )
            if binding is None:
                return None
            model = session.get(AssessmentModelVersion, binding.assessment_model_version_id)
            return self._binding_view(binding, model)

    def bind_round(
        self, scope: AuthorizationScope, round_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        model_id = self._integer(payload.get("assessment_model_version_id"), "model version", 1)
        reason = self._required_text(payload.get("reason"), "reason", 1000)
        with session_scope(self.db_path) as session:
            exam_round = session.get(ExamRound, round_id)
            if exam_round is None:
                raise ValueError("Prüfungsrunde nicht gefunden")
            actor_id = scope.member_for_committee(exam_round.committee_id)
            if actor_id is None or not scope.can_manage_committee(exam_round.committee_id):
                raise PermissionError("Forbidden.")
            model = session.get(AssessmentModelVersion, model_id)
            if model is None:
                raise ValueError("Bewertungsmodellversion nicht gefunden")
            self._assert_model_applicable(session, exam_round, model)
            binding = session.scalar(
                select(ExamRoundAssessmentBinding).where(
                    ExamRoundAssessmentBinding.exam_round_id == round_id
                )
            )
            if binding is not None:
                expected = self._integer(payload.get("version"), "binding version", 1)
                if binding.assessment_model_version_id == model.id:
                    return self._binding_view(binding, model)
                if binding.version != expected:
                    raise ExamResultConflictError(
                        "Die Modellbindung wurde zwischenzeitlich geändert"
                    )
                if self._round_has_assessment_inputs(session, round_id):
                    raise ExamResultConflictError(
                        "Nach der ersten Bewertung kann die Modellversion nicht neu gebunden werden"
                    )
                binding.assessment_model_version_id = model.id
                binding.version += 1
                binding.bound_by_member_id = actor_id
                binding.binding_reason = reason
                binding.bound_at = _now()
            else:
                binding = ExamRoundAssessmentBinding(
                    exam_round_id=round_id,
                    assessment_model_version_id=model.id,
                    version=1,
                    bound_by_member_id=actor_id,
                    binding_reason=reason,
                    bound_at=_now(),
                )
                session.add(binding)
            self._ensure_round_results(session, round_id)
            session.flush()
            return self._binding_view(binding, model)

    # Result lookup and mutation ----------------------------------------------------

    def get_by_slot(self, scope: AuthorizationScope, slot_id: int) -> dict[str, Any] | None:
        with session_scope(self.db_path) as session:
            slot = session.get(ExamSlot, slot_id)
            if slot is None:
                return None
            result = session.scalar(
                select(ExamResult).where(ExamResult.round_candidate_id == slot.round_candidate_id)
            )
            if result is None:
                return None
            self._require_access(session, result, scope)
            return self._view(session, result, scope)

    def get(self, scope: AuthorizationScope, result_id: int) -> dict[str, Any] | None:
        with session_scope(self.db_path) as session:
            result = session.get(ExamResult, result_id)
            if result is None:
                return None
            self._require_access(session, result, scope)
            return self._view(session, result, scope)

    def save_individual(
        self, scope: AuthorizationScope, result_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        expected_version = self._required_result_version(payload)
        component_key = self._required_text(payload.get("component_key"), "component_key", 100)
        criterion_key = self._required_text(payload.get("criterion_key"), "criterion_key", 100)
        submitted = payload.get("submitted", False)
        if not isinstance(submitted, bool):
            raise ValueError("submitted muss ein boolescher Wert sein")
        with session_scope(self.db_path) as session:
            result = self._required_result(session, result_id)
            actor_id, participants, _managed = self._require_access(session, result, scope)
            if actor_id not in participants:
                raise PermissionError("Forbidden.")
            _binding, _model, rules = self._model_context(session, result)
            component = self._component(rules, component_key)
            criterion = self._criterion(component, criterion_key)
            raw_points = self._decimal(payload.get("raw_points"), "raw_points")
            raw_min = Decimal(str(criterion["raw_min"]))
            raw_max = Decimal(str(criterion["raw_max"]))
            if raw_points < raw_min or raw_points > raw_max:
                raise ValueError("Rohpunkte liegen außerhalb der gebundenen Kriterienskala")
            normalized = (raw_points - raw_min) * Decimal(100) / (raw_max - raw_min)
            rationale = self._optional_text(payload.get("rationale"), 4000)
            change_reason = self._optional_text(payload.get("change_reason"), 2000)
            current = self._latest_individual(
                session, result.id, component_key, criterion_key, actor_id
            )
            desired_status = "submitted" if submitted else "draft"
            if current is not None and self._same_individual(
                current, raw_points, normalized, rationale, desired_status
            ):
                return self._view(session, result, scope)
            self._assert_version(result, expected_version)
            self._assert_inputs_mutable(result)
            disclosed = self._is_disclosed(session, result.id, component_key)
            if (disclosed or result.correction_open) and change_reason is None:
                raise ValueError("Eine Änderung nach Offenlegung benötigt eine Begründung")
            day_guards = self._guard_day_mutations(
                session,
                result,
                kind="result_assessment",
                payload=payload,
                actor_member_id=actor_id,
            )
            revision = 1 if current is None else current.revision + 1
            if current is not None:
                current.status = "superseded"
            created_at = _now()
            session.add(
                IndividualAssessment(
                    exam_result_id=result.id,
                    component_key=component_key,
                    criterion_key=criterion_key,
                    assessor_member_id=actor_id,
                    revision=revision,
                    raw_points=_decimal_text(raw_points),
                    normalized_points=_decimal_text(normalized),
                    rationale=rationale,
                    status=desired_status,
                    previous_assessment_id=current.id if current else None,
                    change_reason=change_reason,
                    submitted_at=created_at if submitted else None,
                    created_at=created_at,
                )
            )
            self._touch(result)
            session.flush()
            self._refresh_calculation(session, result, rules)
            self._complete_day_mutations(
                session,
                day_guards,
                actor_member_id=actor_id,
                reason=change_reason,
            )
            return self._view(session, result, scope)

    def withdraw_individual(
        self, scope: AuthorizationScope, result_id: int, assessment_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        expected_version = self._required_result_version(payload)
        with session_scope(self.db_path) as session:
            result = self._required_result(session, result_id)
            actor_id, participants, _managed = self._require_access(session, result, scope)
            current = session.get(IndividualAssessment, assessment_id)
            if (
                current is None
                or current.exam_result_id != result.id
                or current.assessor_member_id != actor_id
                or actor_id not in participants
                or current.status not in {"draft", "submitted"}
            ):
                raise PermissionError("Forbidden.")
            if self._is_disclosed(session, result.id, current.component_key):
                raise ExamResultConflictError(
                    "Nach Offenlegung kann eine Bewertung nur begründet revidiert werden"
                )
            if current.status == "withdrawn":
                return self._view(session, result, scope)
            self._assert_version(result, expected_version)
            self._assert_inputs_mutable(result)
            reason = self._required_text(payload.get("reason"), "reason", 2000)
            day_guards = self._guard_day_mutations(
                session,
                result,
                kind="result_assessment",
                payload=payload,
                actor_member_id=actor_id,
            )
            current.status = "superseded"
            session.add(
                IndividualAssessment(
                    exam_result_id=result.id,
                    component_key=current.component_key,
                    criterion_key=current.criterion_key,
                    assessor_member_id=actor_id,
                    revision=current.revision + 1,
                    raw_points=current.raw_points,
                    normalized_points=current.normalized_points,
                    rationale=current.rationale,
                    status="withdrawn",
                    previous_assessment_id=current.id,
                    change_reason=reason,
                    created_at=_now(),
                )
            )
            self._touch(result)
            session.flush()
            _binding, _model, rules = self._model_context(session, result)
            self._refresh_calculation(session, result, rules)
            self._complete_day_mutations(
                session,
                day_guards,
                actor_member_id=actor_id,
                reason=reason,
            )
            return self._view(session, result, scope)

    def disclose(
        self, scope: AuthorizationScope, result_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        expected_version = self._required_result_version(payload)
        component_key = self._required_text(payload.get("component_key"), "component_key", 100)
        with session_scope(self.db_path) as session:
            result = self._required_result(session, result_id)
            actor_id, participants, can_manage = self._require_access(session, result, scope)
            _binding, _model, rules = self._model_context(session, result)
            component = self._component(rules, component_key)
            existing = session.scalar(
                select(AssessmentDisclosure).where(
                    AssessmentDisclosure.exam_result_id == result.id,
                    AssessmentDisclosure.component_key == component_key,
                )
            )
            if existing is not None:
                return self._view(session, result, scope)
            self._assert_version(result, expected_version)
            self._assert_inputs_mutable(result)
            if actor_id not in participants or not can_manage:
                raise PermissionError("Forbidden.")
            complete = (
                self._individual_component_complete(session, result.id, component, participants)
                if component["mode"] == "committee"
                else self._component_score(
                    session, result.id, component, participants, rules, strict=True
                )
                is not None
            )
            if not complete:
                raise ValueError("Die vorgeschriebenen individuellen Beiträge fehlen")
            day_guards = self._guard_day_mutations(
                session,
                result,
                kind="result_disclosure",
                payload=payload,
                actor_member_id=actor_id,
            )
            session.add(
                AssessmentDisclosure(
                    exam_result_id=result.id,
                    component_key=component_key,
                    disclosed_by_member_id=actor_id,
                    disclosed_at=_now(),
                )
            )
            self._touch(result)
            session.flush()
            self._complete_day_mutations(session, day_guards, actor_member_id=actor_id)
            return self._view(session, result, scope)

    def determine_component(
        self, scope: AuthorizationScope, result_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        expected_version = self._required_result_version(payload)
        component_key = self._required_text(payload.get("component_key"), "component_key", 100)
        points = self._points(payload.get("points"), "points")
        rationale = self._optional_text(payload.get("rationale"), 4000)
        with session_scope(self.db_path) as session:
            result = self._required_result(session, result_id)
            actor_id, actual_participants, can_manage = self._require_access(session, result, scope)
            _binding, _model, rules = self._model_context(session, result)
            component = self._component(rules, component_key)
            if component["mode"] != "committee":
                raise ValueError("Diese Komponente verwendet unabhängige Mehrfachbewertung")
            if actor_id not in actual_participants or not can_manage:
                raise PermissionError("Forbidden.")
            if not self._is_disclosed(session, result.id, component_key):
                raise ValueError("Die individuellen Bewertungen sind noch nicht offengelegt")
            participants = self._participant_set(payload.get("participant_member_ids"))
            self._assert_quorum(rules, participants, actual_participants)
            vote = self._validate_vote(payload.get("vote"), participants)
            dissent = self._validate_dissent(payload.get("dissent", []), participants)
            current = session.scalar(
                select(CommitteeAssessment).where(
                    CommitteeAssessment.exam_result_id == result.id,
                    CommitteeAssessment.component_key == component_key,
                    CommitteeAssessment.status == "current",
                )
            )
            if current is not None and not result.correction_open:
                if (
                    Decimal(current.points) == points
                    and current.rationale == rationale
                    and json.loads(current.participant_member_ids_json) == sorted(participants)
                    and json.loads(current.vote_json) == vote
                    and json.loads(current.dissent_json) == dissent
                ):
                    return self._view(session, result, scope)
                raise ExamResultConflictError(
                    "Eine festgestellte Komponentenbewertung benötigt einen Korrekturvorgang"
                )
            self._assert_version(result, expected_version)
            self._assert_inputs_mutable(result)
            individual_points = [
                Decimal(item.normalized_points)
                for item in self._current_individuals(session, result.id)
                if item.component_key == component_key and item.status == "submitted"
            ]
            if (
                individual_points
                and (points < min(individual_points) or points > max(individual_points))
                and rationale is None
            ):
                raise ValueError(
                    "Eine gemeinsame Bewertung außerhalb der Einzelspanne benötigt eine Begründung"
                )
            day_guards = self._guard_day_mutations(
                session,
                result,
                kind="result_assessment",
                payload=payload,
                actor_member_id=actor_id,
            )
            if current is not None:
                current.status = "superseded"
            session.add(
                CommitteeAssessment(
                    exam_result_id=result.id,
                    component_key=component_key,
                    revision=1 if current is None else current.revision + 1,
                    points=_decimal_text(points),
                    rationale=rationale,
                    participant_member_ids_json=self._json(sorted(participants)),
                    vote_json=self._json(vote),
                    dissent_json=self._json(dissent),
                    status="current",
                    previous_assessment_id=current.id if current else None,
                    determined_by_member_id=actor_id,
                    determined_at=_now(),
                )
            )
            self._touch(result)
            session.flush()
            self._refresh_calculation(session, result, rules)
            self._complete_day_mutations(
                session,
                day_guards,
                actor_member_id=actor_id,
                reason=rationale,
            )
            return self._view(session, result, scope)

    def record_external(
        self, scope: AuthorizationScope, result_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        expected_version = self._required_result_version(payload)
        area_key = self._required_text(payload.get("area_key"), "area_key", 100)
        points = self._points(payload.get("points"), "points")
        with session_scope(self.db_path) as session:
            result = self._required_result(session, result_id)
            actor_id, _participants, can_manage = self._require_access(session, result, scope)
            _binding, _model, rules = self._model_context(session, result)
            self._external_area(rules, area_key)
            self._assert_version(result, expected_version)
            self._assert_inputs_mutable(result)
            if actor_id is None or not can_manage:
                raise PermissionError("Forbidden.")
            current = self._latest_external(session, result.id, area_key)
            correction_reason = self._optional_text(payload.get("correction_reason"), 2000)
            if current is not None and correction_reason is None:
                raise ValueError("Die Korrektur eines Eingangsergebnisses benötigt eine Begründung")
            day_guards = self._guard_day_mutations(
                session,
                result,
                kind="result_external",
                payload=payload,
                actor_member_id=actor_id,
            )
            if current is not None:
                current.status = "replaced"
            session.add(
                ExternalExamResult(
                    exam_result_id=result.id,
                    area_key=area_key,
                    revision=1 if current is None else current.revision + 1,
                    points=_decimal_text(points),
                    grade=self._optional_text(payload.get("grade"), 100),
                    professional_status=self._required_text(
                        payload.get("professional_status"), "professional_status", 300
                    ),
                    determining_authority=self._required_text(
                        payload.get("determining_authority"), "determining_authority", 500
                    ),
                    source_reference=self._required_text(
                        payload.get("source_reference"), "source_reference", 1000
                    ),
                    status="unconfirmed",
                    recorded_by_member_id=actor_id,
                    recorded_at=_now(),
                    previous_external_result_id=current.id if current else None,
                    correction_reason=correction_reason,
                )
            )
            self._touch(result)
            session.flush()
            self._refresh_calculation(session, result, rules)
            self._complete_day_mutations(
                session,
                day_guards,
                actor_member_id=actor_id,
                reason=correction_reason,
            )
            return self._view(session, result, scope)

    def confirm_external(
        self,
        scope: AuthorizationScope,
        result_id: int,
        external_result_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        expected_version = self._required_result_version(payload)
        with session_scope(self.db_path) as session:
            result = self._required_result(session, result_id)
            actor_id, _participants, can_manage = self._require_access(session, result, scope)
            external = session.get(ExternalExamResult, external_result_id)
            if external is None or external.exam_result_id != result.id:
                raise ValueError("Eingangsergebnis nicht gefunden")
            if external.status == "confirmed" and external.confirmed_by_member_id == actor_id:
                return self._view(session, result, scope)
            self._assert_version(result, expected_version)
            self._assert_inputs_mutable(result)
            if actor_id is None or not can_manage:
                raise PermissionError("Forbidden.")
            if external.status != "unconfirmed":
                raise ExamResultConflictError("Das Eingangsergebnis ist nicht mehr unbestätigt")
            if external.recorded_by_member_id == actor_id:
                raise PermissionError("Erfassung und Bestätigung müssen getrennt erfolgen")
            if self._latest_external(session, result.id, external.area_key).id != external.id:
                raise ExamResultConflictError("Das Eingangsergebnis wurde bereits ersetzt")
            day_guards = self._guard_day_mutations(
                session,
                result,
                kind="result_external",
                payload=payload,
                actor_member_id=actor_id,
            )
            external.status = "confirmed"
            external.confirmed_by_member_id = actor_id
            external.confirmed_at = _now()
            self._touch(result)
            session.flush()
            _binding, _model, rules = self._model_context(session, result)
            self._refresh_calculation(session, result, rules)
            self._complete_day_mutations(session, day_guards, actor_member_id=actor_id)
            return self._view(session, result, scope)

    def determine_result(
        self, scope: AuthorizationScope, result_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        expected_version = self._required_result_version(payload)
        with session_scope(self.db_path) as session:
            result = self._required_result(session, result_id)
            actor_id, actual_participants, can_manage = self._require_access(session, result, scope)
            if actor_id not in actual_participants or not can_manage:
                raise PermissionError("Forbidden.")
            _binding, _model, rules = self._model_context(session, result)
            participants = self._participant_set(payload.get("participant_member_ids"))
            self._assert_quorum(rules, participants, actual_participants)
            vote = self._validate_vote(payload.get("vote"), participants)
            dissent = self._validate_dissent(payload.get("dissent", []), participants)
            current = self._current_determination(session, result.id)
            if current is not None and not result.correction_open:
                if (
                    json.loads(current.participant_member_ids_json) == sorted(participants)
                    and json.loads(current.vote_json) == vote
                    and json.loads(current.dissent_json) == dissent
                ):
                    return self._view(session, result, scope)
                raise ExamResultConflictError("Das Ergebnis wurde bereits festgestellt")
            self._assert_version(result, expected_version)
            calculation = self._refresh_calculation(session, result, rules)
            if calculation is None:
                raise ValueError("Das Ergebnis ist noch nicht berechnungsbereit")
            day_guards = self._guard_day_mutations(
                session,
                result,
                kind="result_determine",
                payload=payload,
                actor_member_id=actor_id,
            )
            correction = session.scalar(
                select(ResultCorrection).where(
                    ResultCorrection.exam_result_id == result.id,
                    ResultCorrection.status == "open",
                )
            )
            if current is not None:
                current.status = "superseded"
                for communication in session.scalars(
                    select(ResultCommunication).where(
                        ResultCommunication.result_determination_id == current.id,
                        ResultCommunication.status == "current",
                    )
                ):
                    communication.status = "obsolete"
                for export in session.scalars(
                    select(ResultExport).where(
                        ResultExport.result_determination_id == current.id,
                        ResultExport.status == "determined",
                    )
                ):
                    export.status = "superseded"
            revision = 1 if current is None else current.revision + 1
            determination = ResultDetermination(
                exam_result_id=result.id,
                revision=revision,
                result_calculation_id=calculation.id,
                participant_member_ids_json=self._json(sorted(participants)),
                vote_json=self._json(vote),
                dissent_json=self._json(dissent),
                status="current",
                previous_determination_id=current.id if current else None,
                correction_id=correction.id if correction else None,
                determined_by_member_id=actor_id,
                determined_at=_now(),
            )
            session.add(determination)
            if correction is not None:
                correction.status = "completed"
                correction.completed_at = determination.determined_at
            result.current_state = "determined"
            result.correction_open = 0
            self._touch(result)
            session.flush()
            self._complete_day_mutations(session, day_guards, actor_member_id=actor_id)
            return self._view(session, result, scope)

    def confirm_record(
        self, scope: AuthorizationScope, result_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        expected_version = self._required_result_version(payload)
        with session_scope(self.db_path) as session:
            result = self._required_result(session, result_id)
            actor_id, _actual, _managed = self._require_access(session, result, scope)
            determination = self._current_determination(session, result.id)
            if determination is None:
                raise ValueError("Es liegt noch keine Ergebnisfeststellung vor")
            participants = set(json.loads(determination.participant_member_ids_json))
            if actor_id not in participants:
                raise PermissionError("Forbidden.")
            existing = session.scalar(
                select(ResultRecordConfirmation).where(
                    ResultRecordConfirmation.result_determination_id == determination.id,
                    ResultRecordConfirmation.committee_member_id == actor_id,
                )
            )
            if existing is not None:
                return self._view(session, result, scope)
            self._assert_version(result, expected_version)
            if result.correction_open:
                raise ExamResultConflictError(
                    "Während einer Korrektur kann die Niederschrift nicht bestätigt werden"
                )
            day_guards = self._guard_day_mutations(
                session,
                result,
                kind="result_confirm_record",
                payload=payload,
                actor_member_id=actor_id,
            )
            session.add(
                ResultRecordConfirmation(
                    result_determination_id=determination.id,
                    committee_member_id=actor_id,
                    confirmed_at=_now(),
                )
            )
            self._touch(result)
            session.flush()
            self._complete_day_mutations(session, day_guards, actor_member_id=actor_id)
            return self._view(session, result, scope)

    def open_correction(
        self, scope: AuthorizationScope, result_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        expected_version = self._required_result_version(payload)
        reason = self._required_text(payload.get("reason"), "reason", 3000)
        with session_scope(self.db_path) as session:
            result = self._required_result(session, result_id)
            actor_id, _participants, can_manage = self._require_access(session, result, scope)
            if actor_id is None or not can_manage:
                raise PermissionError("Forbidden.")
            current = self._current_determination(session, result.id)
            if current is None:
                raise ValueError("Nur ein festgestelltes Ergebnis kann korrigiert werden")
            existing = session.scalar(
                select(ResultCorrection).where(
                    ResultCorrection.exam_result_id == result.id,
                    ResultCorrection.status == "open",
                )
            )
            if existing is not None and existing.reason == reason:
                return self._view(session, result, scope)
            self._assert_version(result, expected_version)
            if existing is not None:
                raise ExamResultConflictError("Für das Ergebnis ist bereits eine Korrektur offen")
            day_guards = self._guard_day_mutations(
                session,
                result,
                kind="result_correction",
                payload=payload,
                actor_member_id=actor_id,
            )
            reopening_reference = self._optional_text(payload.get("reopening_reference"), 1000)
            if self._has_completed_day(session, result) and reopening_reference is None:
                raise ValueError(
                    "Nach Tagesabschluss ist eine zulässige Wiederöffnung nach #36 erforderlich"
                )
            session.add(
                ResultCorrection(
                    exam_result_id=result.id,
                    result_determination_id=current.id,
                    reason=reason,
                    requested_by_member_id=actor_id,
                    status="open",
                    reopening_reference=reopening_reference,
                    requested_at=_now(),
                )
            )
            result.correction_open = 1
            self._touch(result)
            session.flush()
            self._complete_day_mutations(
                session,
                day_guards,
                actor_member_id=actor_id,
                reason=reason,
            )
            return self._view(session, result, scope)

    def communicate(
        self, scope: AuthorizationScope, result_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        expected_version = self._required_result_version(payload)
        method = self._required_text(payload.get("method"), "method", 300)
        communicated_at = self._required_datetime(payload.get("communicated_at"), "communicated_at")
        with session_scope(self.db_path) as session:
            result = self._required_result(session, result_id)
            actor_id, _participants, can_manage = self._require_access(session, result, scope)
            if actor_id is None or not can_manage:
                raise PermissionError("Forbidden.")
            determination = self._current_determination(session, result.id)
            if determination is None or result.correction_open:
                raise ValueError("Nur der aktuelle festgestellte Stand kann mitgeteilt werden")
            participants = set(json.loads(determination.participant_member_ids_json))
            confirmations = self._confirmation_ids(session, determination.id)
            if confirmations != participants:
                raise ValueError("Die Ergebnisniederschrift ist noch nicht vollständig bestätigt")
            existing = session.scalar(
                select(ResultCommunication).where(
                    ResultCommunication.exam_result_id == result.id,
                    ResultCommunication.result_determination_id == determination.id,
                    ResultCommunication.status == "current",
                )
            )
            if (
                existing is not None
                and existing.method == method
                and existing.communicated_at == communicated_at
            ):
                return self._view(session, result, scope)
            self._assert_version(result, expected_version)
            day_guards = self._guard_day_mutations(
                session,
                result,
                kind="result_communicate",
                payload=payload,
                actor_member_id=actor_id,
            )
            if existing is not None:
                existing.status = "obsolete"
            session.add(
                ResultCommunication(
                    exam_result_id=result.id,
                    result_determination_id=determination.id,
                    method=method,
                    responsible_member_id=actor_id,
                    communicated_at=communicated_at,
                    external_document_status=self._optional_text(
                        payload.get("external_document_status"), 300
                    ),
                    external_document_reference=self._optional_text(
                        payload.get("external_document_reference"), 1000
                    ),
                    status="current",
                    created_at=_now(),
                )
            )
            result.current_state = "communicated"
            self._touch(result)
            session.flush()
            self._complete_day_mutations(session, day_guards, actor_member_id=actor_id)
            return self._view(session, result, scope)

    def set_retention(
        self, scope: AuthorizationScope, result_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        allowed_fields = {
            "version",
            "period_start",
            "retain_until",
            "legal_hold",
            "hold_reason",
            "release_reason",
        }
        if set(payload) - allowed_fields:
            raise ValueError("Die Aufbewahrungsregel enthält unzulässige Felder")
        expected_version = self._required_result_version(payload)
        period_start = self._optional_date(payload.get("period_start"), "period_start")
        retain_until = self._optional_date(payload.get("retain_until"), "retain_until")
        legal_hold = payload.get("legal_hold", False)
        if not isinstance(legal_hold, bool):
            raise ValueError("legal_hold muss ein boolescher Wert sein")
        hold_reason = self._optional_text(payload.get("hold_reason"), 3000)
        if legal_hold and hold_reason is None:
            raise ValueError("Eine Aufbewahrungssperre benötigt eine Begründung")
        with session_scope(self.db_path) as session:
            result = self._required_result(session, result_id)
            actor_id, _participants, can_manage = self._require_access(session, result, scope)
            if actor_id is None or not can_manage:
                raise PermissionError("Forbidden.")
            _binding, model, _rules = self._model_context(session, result)
            if retain_until is not None and period_start is None:
                raise ValueError("Eine Aufbewahrungsfrist benötigt einen Fristbeginn")
            if period_start is not None:
                minimum = self._add_years(period_start, model.retention_years)
                if retain_until is None or retain_until < minimum:
                    raise ValueError(
                        "Die regelgebundene Mindestaufbewahrung darf nicht verkürzt werden"
                    )
            existing = session.scalar(
                select(ResultRetention).where(ResultRetention.exam_result_id == result.id)
            )
            if (
                existing is not None
                and existing.retain_until is not None
                and (retain_until is None or retain_until.isoformat() < existing.retain_until)
            ):
                raise ValueError("Eine verbindliche Aufbewahrungsfrist darf nicht verkürzt werden")
            if existing is not None and bool(existing.legal_hold) and not legal_hold:
                release_reason = self._optional_text(payload.get("release_reason"), 3000)
                if release_reason is None:
                    raise ValueError("Das Aufheben einer Sperre benötigt eine Begründung")
                hold_reason = f"Freigabe: {release_reason}"
            period_start_text = period_start.isoformat() if period_start else None
            retain_until_text = retain_until.isoformat() if retain_until else None
            if (
                existing is not None
                and existing.rule_reference == model.retention_rule_reference
                and existing.period_start == period_start_text
                and existing.retain_until == retain_until_text
                and bool(existing.legal_hold) == legal_hold
                and existing.hold_reason == hold_reason
            ):
                return self._view(session, result, scope)
            self._assert_version(result, expected_version)
            day_guards = self._guard_day_mutations(
                session,
                result,
                kind="result_retention",
                payload=payload,
                actor_member_id=actor_id,
            )
            if existing is None:
                existing = ResultRetention(
                    exam_result_id=result.id,
                    rule_reference=model.retention_rule_reference,
                    updated_by_member_id=actor_id,
                )
                session.add(existing)
            existing.rule_reference = model.retention_rule_reference
            existing.period_start = period_start_text
            existing.retain_until = retain_until_text
            existing.legal_hold = int(legal_hold)
            existing.hold_reason = hold_reason
            existing.updated_by_member_id = actor_id
            existing.updated_at = _now()
            self._touch(result)
            session.flush()
            self._complete_day_mutations(session, day_guards, actor_member_id=actor_id)
            return self._view(session, result, scope)

    # Completion and exports --------------------------------------------------------

    def completion_for_day(self, scope: AuthorizationScope, day_id: int) -> dict[str, Any] | None:
        with session_scope(self.db_path) as session:
            day = session.get(ExamDay, day_id)
            if day is None:
                return None
            exam_round = session.get(ExamRound, day.exam_round_id)
            if exam_round is None or not scope.can_read_committee(exam_round.committee_id):
                raise PermissionError("Forbidden.")
            slots = list(
                session.scalars(
                    select(ExamSlot).where(ExamSlot.exam_day_id == day.id).order_by(ExamSlot.id)
                )
            )
            rows = []
            for slot in slots:
                result = session.scalar(
                    select(ExamResult).where(
                        ExamResult.round_candidate_id == slot.round_candidate_id
                    )
                )
                if result is None:
                    rows.append(
                        {
                            "exam_slot_id": slot.id,
                            "exam_result_id": None,
                            "state": "not_bound",
                            "day_assessments": [],
                            "day_assessments_complete": False,
                            "external_inputs_pending": [],
                            "overall_determination_pending": False,
                            "record_confirmations_complete": False,
                            "regular_close_ready": slot.execution_status in {"cancelled"},
                        }
                    )
                    continue
                if result.legacy_status:
                    rows.append(
                        {
                            "exam_slot_id": slot.id,
                            "exam_result_id": result.id,
                            "state": result.legacy_status,
                            "day_assessments": [],
                            "day_assessments_complete": True,
                            "external_inputs_pending": [],
                            "overall_determination_pending": False,
                            "record_confirmations_complete": True,
                            "regular_close_ready": True,
                        }
                    )
                    continue
                _binding, _model, rules = self._model_context(session, result)
                participants = self._participant_ids(session, result)
                day_assessments = [
                    {
                        "component_key": component["key"],
                        "label": component["label"],
                        "complete": self._component_score(
                            session,
                            result.id,
                            component,
                            participants,
                            rules,
                            strict=False,
                        )
                        is not None,
                    }
                    for component in rules["components"]
                    if component.get("day_scoped", False)
                ]
                day_complete = all(item["complete"] for item in day_assessments)
                external_pending = [
                    area["key"]
                    for area in rules["external_areas"]
                    if area["required"]
                    and (
                        (external := self._latest_external(session, result.id, area["key"])) is None
                        or external.status != "confirmed"
                    )
                ]
                determination = self._current_determination(session, result.id)
                confirmations_complete = determination is None or self._confirmation_ids(
                    session, determination.id
                ) == set(json.loads(determination.participant_member_ids_json))
                pending = result.current_state == "calculation_ready"
                rows.append(
                    {
                        "exam_slot_id": slot.id,
                        "exam_result_id": result.id,
                        "state": result.current_state,
                        "correction_open": bool(result.correction_open),
                        "day_assessments": day_assessments,
                        "day_assessments_complete": day_complete,
                        "external_inputs_pending": external_pending,
                        "overall_determination_pending": pending,
                        "record_confirmations_complete": confirmations_complete,
                        "regular_close_ready": day_complete
                        and not pending
                        and confirmations_complete
                        and not bool(result.correction_open),
                    }
                )
            return {
                "exam_day_id": day.id,
                "slots": rows,
                "closing_ready": all(row["regular_close_ready"] for row in rows),
            }

    def machine_export(self, scope: AuthorizationScope, result_id: int) -> dict[str, Any]:
        with session_scope(self.db_path) as session:
            result = self._required_result(session, result_id)
            actor_id, _participants, _managed = self._require_access(session, result, scope)
            if actor_id is None:
                raise PermissionError("Forbidden.")
            determination = self._current_determination(session, result.id)
            status = "determined" if determination is not None else "draft"
            session.add(
                ResultExport(
                    exam_result_id=result.id,
                    result_determination_id=determination.id if determination else None,
                    export_kind="machine",
                    status=status,
                    generated_by_member_id=actor_id,
                    generated_at=_now(),
                )
            )
            session.flush()
            view = self._view(session, result, scope)
            return {
                "export_status": status,
                "official_document": False,
                "model_version": view["model_version"],
                "candidate": view["candidate"],
                "result": view,
            }

    def human_export(self, scope: AuthorizationScope, result_id: int) -> str:
        with session_scope(self.db_path) as session:
            aggregate = self._required_result(session, result_id)
            actor_id, _participants, _managed = self._require_access(session, aggregate, scope)
            if actor_id is None:
                raise PermissionError("Forbidden.")
            determination = self._current_determination(session, aggregate.id)
            session.add(
                ResultExport(
                    exam_result_id=aggregate.id,
                    result_determination_id=determination.id if determination else None,
                    export_kind="human",
                    status="determined" if determination is not None else "draft",
                    generated_by_member_id=actor_id,
                    generated_at=_now(),
                )
            )
            session.flush()
            result = self._view(session, aggregate, scope)
        calculation = result["current_calculation"]
        determination = result["current_determination"]
        candidate = result["candidate"]
        marker = "FESTGESTELLT" if determination else "ENTWURF"
        lines = [
            f"Ergebnisniederschrift {result['id']} – {marker}",
            "Kein amtliches IHK-Dokument",
            f"Prüfling: {candidate['first_name']} {candidate['last_name']}",
            f"IHK-Prüfungsnummer: {candidate['ihk_exam_number']}",
            f"Bewertungsmodell: {result['model_version']['model_key']} "
            f"v{result['model_version']['version']}",
            f"Zustand: {result['state']}",
            "",
            "Bestätigte externe Eingangsergebnisse:",
        ]
        confirmed_external = [
            item for item in result["external_results"] if item["status"] == "confirmed"
        ]
        lines.extend(
            f"- {item['area_key']}: {item['points']} Punkte ({item['source_reference']})"
            for item in confirmed_external
        )
        if not confirmed_external:
            lines.append("- keine")
        lines.extend(["", "Festgestellte Komponentenbewertungen:"])
        lines.extend(
            f"- {item['component_key']}: {item['points']} Punkte"
            for item in result["committee_assessments"]
            if item["status"] == "current"
        )
        if calculation:
            lines.extend(
                [
                    "",
                    "Berechnungsweg:",
                    *[
                        f"- {item['kind']} {item['key']}: {item['points']} × {item['weight']} %"
                        for item in calculation["path"]["inputs"]
                    ],
                    f"Gesamtergebnis: {calculation['total_points']} Punkte, "
                    f"{calculation['grade']}, "
                    f"{'bestanden' if calculation['passed'] else 'nicht bestanden'}",
                ]
            )
        if determination:
            lines.extend(
                [
                    "",
                    f"Feststellung: Version {determination['revision']} am "
                    f"{determination['determined_at']}",
                    "Mitwirkende: "
                    + ", ".join(str(item) for item in determination["participant_member_ids"]),
                    "Bestätigungen: "
                    + ", ".join(str(item) for item in determination["confirmation_member_ids"]),
                ]
            )
            if determination["dissent"]:
                lines.append("Abweichende Voten: " + self._json(determination["dissent"]))
        if result["correction_open"]:
            lines.append("Korrekturvorgang: offen")
        if result["communications"]:
            current = next(
                (item for item in result["communications"] if item["status"] == "current"), None
            )
            if current:
                lines.append(
                    f"Ergebnismitteilung: {current['communicated_at']} ({current['method']})"
                )
        return "\n".join(lines) + "\n"

    # Internal calculation and view helpers ----------------------------------------

    def _refresh_calculation(
        self, session: Session, result: ExamResult, rules: dict[str, Any]
    ) -> ResultCalculation | None:
        participants = self._participant_ids(session, result)
        inputs: list[dict[str, Any]] = []
        weighted_total = Decimal(0)
        scores: dict[str, Decimal] = {}
        for component in rules["components"]:
            score = self._component_score(
                session, result.id, component, participants, rules, strict=True
            )
            if score is None:
                if self._current_determination(session, result.id) is None:
                    result.current_state = "incomplete"
                return None
            weighted_total += score * Decimal(str(component["weight"])) / Decimal(100)
            scores[component["key"]] = score
            inputs.append(
                {
                    "kind": "component",
                    "key": component["key"],
                    "points": _decimal_text(score),
                    "weight": str(component["weight"]),
                }
            )
        for area in rules["external_areas"]:
            external = self._latest_external(session, result.id, area["key"])
            if area["required"] and (external is None or external.status != "confirmed"):
                if self._current_determination(session, result.id) is None:
                    result.current_state = "incomplete"
                return None
            if external is None or external.status != "confirmed":
                continue
            score = Decimal(external.points)
            weighted_total += score * Decimal(str(area["weight"])) / Decimal(100)
            scores[area["key"]] = score
            inputs.append(
                {
                    "kind": "external",
                    "key": area["key"],
                    "points": external.points,
                    "weight": str(area["weight"]),
                    "revision_id": external.id,
                }
            )
        outcome = self._outcome(rules, weighted_total, scores)
        rounded_total = outcome["rounded_total"]
        grade = outcome["grade"]
        passed = outcome["passed"]
        fingerprint_payload = {
            "model": self._model_context(session, result)[1].id,
            "inputs": inputs,
            "unrounded_total": _decimal_text(weighted_total),
        }
        fingerprint = hashlib.sha256(self._json(fingerprint_payload).encode("utf-8")).hexdigest()
        calculation = session.scalar(
            select(ResultCalculation).where(
                ResultCalculation.exam_result_id == result.id,
                ResultCalculation.input_fingerprint == fingerprint,
            )
        )
        if calculation is None:
            version = (
                session.scalar(
                    select(func.max(ResultCalculation.version)).where(
                        ResultCalculation.exam_result_id == result.id
                    )
                )
                or 0
            ) + 1
            calculation = ResultCalculation(
                exam_result_id=result.id,
                version=version,
                input_fingerprint=fingerprint,
                total_points=_decimal_text(rounded_total),
                grade=grade,
                passed=int(passed),
                calculation_path_json=self._json(
                    {
                        "inputs": inputs,
                        "unrounded_total": _decimal_text(weighted_total),
                        "rounded_total": _decimal_text(rounded_total),
                        "threshold_basis": rules["rounding"]["threshold_basis"],
                    }
                ),
                created_at=_now(),
            )
            session.add(calculation)
            session.flush()
        if self._current_determination(session, result.id) is None:
            result.current_state = "calculation_ready"
        return calculation

    @classmethod
    def _outcome(
        cls,
        rules: dict[str, Any],
        weighted_total: Decimal,
        scores: dict[str, Decimal],
    ) -> dict[str, Any]:
        rounded_total = cls._round(weighted_total, rules["rounding"]["overall"])
        threshold_value = (
            rounded_total if rules["rounding"]["threshold_basis"] == "rounded" else weighted_total
        )
        grade = next(
            item["label"]
            for item in rules["grades"]
            if threshold_value >= Decimal(str(item["min_points"]))
        )
        passing = rules["passing"]
        passed = threshold_value >= Decimal(str(passing["overall_min"]))
        passed = passed and all(
            scores.get(key, Decimal(-1)) >= Decimal(str(minimum))
            for key, minimum in passing["component_minima"].items()
        )
        passed = passed and all(
            scores.get(key, Decimal(-1)) >= Decimal(str(minimum))
            for key, minimum in passing["external_minima"].items()
        )
        return {
            "rounded_total": rounded_total,
            "threshold_value": threshold_value,
            "grade": grade,
            "passed": passed,
        }

    def _component_score(
        self,
        session: Session,
        result_id: int,
        component: dict[str, Any],
        participants: set[int],
        rules: dict[str, Any],
        *,
        strict: bool,
    ) -> Decimal | None:
        if component["mode"] == "committee":
            assessment = session.scalar(
                select(CommitteeAssessment).where(
                    CommitteeAssessment.exam_result_id == result_id,
                    CommitteeAssessment.component_key == component["key"],
                    CommitteeAssessment.status == "current",
                )
            )
            return Decimal(assessment.points) if assessment else None
        current = [
            item
            for item in self._current_individuals(session, result_id)
            if item.component_key == component["key"] and item.status == "submitted"
        ]
        by_assessor: dict[int, dict[str, IndividualAssessment]] = {}
        for item in current:
            if item.assessor_member_id in participants:
                by_assessor.setdefault(item.assessor_member_id, {})[item.criterion_key] = item
        criteria = component["criteria"]
        complete_scores: list[Decimal] = []
        for assessments in by_assessor.values():
            if set(assessments) != {criterion["key"] for criterion in criteria}:
                continue
            score = sum(
                Decimal(assessments[criterion["key"]].normalized_points)
                * Decimal(str(criterion["weight"]))
                / Decimal(100)
                for criterion in criteria
            )
            complete_scores.append(self._round(score, rules["rounding"]["intermediate"]))
        required = int(component["required_assessors"])
        if len(complete_scores) < required:
            return None
        deviation = max(complete_scores) - min(complete_scores)
        if (
            component["additional_assessor_on_deviation"]
            and deviation > Decimal(str(component["max_deviation"]))
            and len(complete_scores) < required + 1
        ):
            return None
        return sum(complete_scores, Decimal(0)) / Decimal(len(complete_scores))

    def _view(
        self, session: Session, result: ExamResult, scope: AuthorizationScope
    ) -> dict[str, Any]:
        actor_id, participants, can_manage = self._access(session, result, scope)
        binding, model, rules = self._model_context(session, result)
        round_candidate = session.get(RoundCandidate, result.round_candidate_id)
        candidate = session.get(Candidate, round_candidate.candidate_id)
        disclosures = {
            item.component_key: item
            for item in session.scalars(
                select(AssessmentDisclosure).where(AssessmentDisclosure.exam_result_id == result.id)
            )
        }
        visible_individuals = []
        for item in self._all_individuals(session, result.id):
            disclosed = item.component_key in disclosures
            if item.assessor_member_id != actor_id and not (disclosed and actor_id in participants):
                continue
            visible_individuals.append(self._individual_view(item))
        committee = list(
            session.scalars(
                select(CommitteeAssessment)
                .where(CommitteeAssessment.exam_result_id == result.id)
                .order_by(CommitteeAssessment.component_key, CommitteeAssessment.revision)
            )
        )
        external = list(
            session.scalars(
                select(ExternalExamResult)
                .where(ExternalExamResult.exam_result_id == result.id)
                .order_by(ExternalExamResult.area_key, ExternalExamResult.revision)
            )
        )
        calculations = list(
            session.scalars(
                select(ResultCalculation)
                .where(ResultCalculation.exam_result_id == result.id)
                .order_by(ResultCalculation.version)
            )
        )
        current_calculation = self._refresh_calculation(session, result, rules)
        determinations = list(
            session.scalars(
                select(ResultDetermination)
                .where(ResultDetermination.exam_result_id == result.id)
                .order_by(ResultDetermination.revision)
            )
        )
        corrections = list(
            session.scalars(
                select(ResultCorrection)
                .where(ResultCorrection.exam_result_id == result.id)
                .order_by(ResultCorrection.id)
            )
        )
        communications = list(
            session.scalars(
                select(ResultCommunication)
                .where(ResultCommunication.exam_result_id == result.id)
                .order_by(ResultCommunication.id)
            )
        )
        retention = session.scalar(
            select(ResultRetention).where(ResultRetention.exam_result_id == result.id)
        )
        exports = list(
            session.scalars(
                select(ResultExport)
                .where(ResultExport.exam_result_id == result.id)
                .order_by(ResultExport.id)
            )
        )
        current_determination = next(
            (item for item in determinations if item.status == "current"), None
        )
        result_days = days_for_result(session, result.id)
        content_mutable = True
        for day in result_days:
            if day.closure_status == "open":
                continue
            if day.closure_status == "reopening":
                reopening = session.scalar(
                    select(ExamDayReopening).where(
                        ExamDayReopening.exam_day_id == day.id,
                        ExamDayReopening.status == "open",
                    )
                )
                if reopening is not None and f"exam_result:{result.id}" in set(
                    json.loads(reopening.scope_json)
                ):
                    continue
            content_mutable = False
            break
        return {
            "id": result.id,
            "round_candidate_id": result.round_candidate_id,
            "day_revisions": {str(day.id): day.revision for day in result_days},
            "version": result.version,
            "state": result.current_state,
            "correction_open": bool(result.correction_open),
            "legacy_status": result.legacy_status,
            "candidate": {
                "id": candidate.id,
                "first_name": candidate.first_name,
                "last_name": candidate.last_name,
                "ihk_exam_number": candidate.ihk_exam_number,
                "specialization": candidate.specialization,
            },
            "binding": self._binding_view(binding, model),
            "model_version": self._model_view(model),
            "participants": sorted(participants),
            "disclosures": [
                {
                    "component_key": key,
                    "disclosed_by_member_id": item.disclosed_by_member_id,
                    "disclosed_at": item.disclosed_at,
                }
                for key, item in sorted(disclosures.items())
            ],
            "individual_assessments": visible_individuals,
            "individual_assessment_counts": self._individual_counts(session, result.id),
            "committee_assessments": [self._committee_view(item) for item in committee],
            "external_results": [self._external_view(item) for item in external],
            "calculations": [self._calculation_view(item) for item in calculations],
            "current_calculation": (
                self._calculation_view(current_calculation) if current_calculation else None
            ),
            "determinations": [self._determination_view(session, item) for item in determinations],
            "current_determination": (
                self._determination_view(session, current_determination)
                if current_determination
                else None
            ),
            "corrections": [self._correction_view(item) for item in corrections],
            "communications": [self._communication_view(item) for item in communications],
            "retention": self._retention_view(retention) if retention else None,
            "exports": [self._export_view(item) for item in exports],
            "permissions": {
                "assess_own": content_mutable and actor_id in participants,
                "disclose": content_mutable and actor_id in participants and can_manage,
                "determine_component": content_mutable and actor_id in participants and can_manage,
                "manage_external": can_manage,
                "determine_result": actor_id in participants and can_manage,
                "confirm_record": actor_id in participants,
                "coordinate_correction": content_mutable and can_manage,
                "communicate": can_manage,
                "manage_retention": can_manage,
            },
            "created_at": result.created_at,
            "updated_at": result.updated_at,
            "_links": {
                "self": {"href": f"/api/exam-results/{result.id}"},
                "machine_export": {"href": f"/api/exam-results/{result.id}/export.json"},
                "human_export": {"href": f"/api/exam-results/{result.id}/export.txt"},
            },
        }

    # Context, validation, and serialization helpers --------------------------------

    @staticmethod
    def _guard_day_mutations(
        session: Session,
        result: ExamResult,
        *,
        kind: str,
        payload: dict[str, Any],
        actor_member_id: int | None,
    ) -> list[DayMutationGuard]:
        return [
            guard_day_mutation(
                session,
                day=day,
                kind=kind,
                entity_id=result.id,
                payload=payload,
                actor_member_id=actor_member_id,
            )
            for day in days_for_result(session, result.id)
        ]

    @staticmethod
    def _complete_day_mutations(
        session: Session,
        guards: list[DayMutationGuard],
        *,
        actor_member_id: int,
        reason: str | None = None,
    ) -> None:
        for guard in guards:
            complete_day_mutation(
                session,
                guard,
                actor_member_id=actor_member_id,
                reason=reason,
            )

    def _model_context(
        self, session: Session, result: ExamResult
    ) -> tuple[ExamRoundAssessmentBinding, AssessmentModelVersion, dict[str, Any]]:
        round_candidate = session.get(RoundCandidate, result.round_candidate_id)
        binding = session.scalar(
            select(ExamRoundAssessmentBinding).where(
                ExamRoundAssessmentBinding.exam_round_id == round_candidate.exam_round_id
            )
        )
        if binding is None:
            raise ValueError("Die Prüfungsrunde ist noch an kein Bewertungsmodell gebunden")
        model = session.get(AssessmentModelVersion, binding.assessment_model_version_id)
        if model is None:  # pragma: no cover - protected by the database constraint
            raise RuntimeError("Gebundene Bewertungsmodellversion fehlt")
        return binding, model, json.loads(model.rules_json)

    def _require_access(
        self, session: Session, result: ExamResult, scope: AuthorizationScope
    ) -> tuple[int | None, set[int], bool]:
        actor_id, participants, can_manage = self._access(session, result, scope)
        if actor_id not in participants and not can_manage:
            raise PermissionError("Forbidden.")
        return actor_id, participants, can_manage

    def _access(
        self, session: Session, result: ExamResult, scope: AuthorizationScope
    ) -> tuple[int | None, set[int], bool]:
        round_candidate = session.get(RoundCandidate, result.round_candidate_id)
        exam_round = session.get(ExamRound, round_candidate.exam_round_id)
        actor_id = scope.member_for_committee(exam_round.committee_id)
        return (
            actor_id,
            self._participant_ids(session, result),
            scope.can_manage_committee(exam_round.committee_id),
        )

    @staticmethod
    def _required_result(session: Session, result_id: int) -> ExamResult:
        result = session.get(ExamResult, result_id)
        if result is None:
            raise ValueError("Ergebnisvorgang nicht gefunden")
        if result.legacy_status is not None:
            raise ValueError("Für diesen Altvorgang liegen keine Ergebnisdaten in lzug vor")
        return result

    @staticmethod
    def _assert_version(result: ExamResult, expected_version: int) -> None:
        if result.version != expected_version:
            raise ExamResultConflictError("Der Ergebnisstand wurde zwischenzeitlich geändert")

    @staticmethod
    def _assert_inputs_mutable(result: ExamResult) -> None:
        if result.current_state in {"determined", "communicated"} and not result.correction_open:
            raise ExamResultConflictError(
                "Ein festgestelltes Ergebnis benötigt einen begründeten Korrekturvorgang"
            )

    @staticmethod
    def _touch(result: ExamResult) -> None:
        result.version += 1
        result.updated_at = _now()

    def _participant_ids(self, session: Session, result: ExamResult) -> set[int]:
        round_candidate = session.get(RoundCandidate, result.round_candidate_id)
        return set(
            session.scalars(
                select(ExamProtocolParticipant.committee_member_id)
                .join(
                    ExamProtocol,
                    ExamProtocol.id == ExamProtocolParticipant.exam_protocol_id,
                )
                .join(ExamSlot, ExamSlot.id == ExamProtocol.exam_slot_id)
                .where(ExamSlot.round_candidate_id == round_candidate.id)
            )
        )

    @staticmethod
    def _latest_individual(
        session: Session,
        result_id: int,
        component_key: str,
        criterion_key: str,
        assessor_id: int,
    ) -> IndividualAssessment | None:
        return session.scalar(
            select(IndividualAssessment)
            .where(
                IndividualAssessment.exam_result_id == result_id,
                IndividualAssessment.component_key == component_key,
                IndividualAssessment.criterion_key == criterion_key,
                IndividualAssessment.assessor_member_id == assessor_id,
                IndividualAssessment.status.in_({"draft", "submitted", "withdrawn"}),
            )
            .order_by(IndividualAssessment.revision.desc())
        )

    @staticmethod
    def _all_individuals(session: Session, result_id: int) -> list[IndividualAssessment]:
        return list(
            session.scalars(
                select(IndividualAssessment)
                .where(IndividualAssessment.exam_result_id == result_id)
                .order_by(
                    IndividualAssessment.component_key,
                    IndividualAssessment.criterion_key,
                    IndividualAssessment.assessor_member_id,
                    IndividualAssessment.revision,
                )
            )
        )

    def _current_individuals(self, session: Session, result_id: int) -> list[IndividualAssessment]:
        latest: dict[tuple[str, str, int], IndividualAssessment] = {}
        for item in self._all_individuals(session, result_id):
            if item.status != "superseded":
                latest[(item.component_key, item.criterion_key, item.assessor_member_id)] = item
        return list(latest.values())

    @staticmethod
    def _same_individual(
        current: IndividualAssessment,
        raw: Decimal,
        normalized: Decimal,
        rationale: str | None,
        status: str,
    ) -> bool:
        return (
            Decimal(current.raw_points) == raw
            and Decimal(current.normalized_points) == normalized
            and current.rationale == rationale
            and current.status == status
        )

    @staticmethod
    def _is_disclosed(session: Session, result_id: int, component_key: str) -> bool:
        return (
            session.scalar(
                select(AssessmentDisclosure.id).where(
                    AssessmentDisclosure.exam_result_id == result_id,
                    AssessmentDisclosure.component_key == component_key,
                )
            )
            is not None
        )

    def _individual_component_complete(
        self,
        session: Session,
        result_id: int,
        component: dict[str, Any],
        participants: set[int],
    ) -> bool:
        criteria = {item["key"] for item in component["criteria"]}
        complete: set[int] = set()
        by_member: dict[int, set[str]] = {}
        for item in self._current_individuals(session, result_id):
            if item.component_key == component["key"] and item.status == "submitted":
                by_member.setdefault(item.assessor_member_id, set()).add(item.criterion_key)
        for member_id, submitted in by_member.items():
            if member_id in participants and submitted == criteria:
                complete.add(member_id)
        return len(complete) >= int(component["required_assessors"])

    @staticmethod
    def _latest_external(
        session: Session, result_id: int, area_key: str
    ) -> ExternalExamResult | None:
        return session.scalar(
            select(ExternalExamResult)
            .where(
                ExternalExamResult.exam_result_id == result_id,
                ExternalExamResult.area_key == area_key,
                ExternalExamResult.status.in_({"unconfirmed", "confirmed"}),
            )
            .order_by(ExternalExamResult.revision.desc())
        )

    @staticmethod
    def _current_determination(session: Session, result_id: int) -> ResultDetermination | None:
        return session.scalar(
            select(ResultDetermination).where(
                ResultDetermination.exam_result_id == result_id,
                ResultDetermination.status == "current",
            )
        )

    @staticmethod
    def _confirmation_ids(session: Session, determination_id: int) -> set[int]:
        return set(
            session.scalars(
                select(ResultRecordConfirmation.committee_member_id).where(
                    ResultRecordConfirmation.result_determination_id == determination_id
                )
            )
        )

    def _has_completed_day(self, session: Session, result: ExamResult) -> bool:
        return (
            session.scalar(
                select(ExamDay.id)
                .join(ExamSlot, ExamSlot.exam_day_id == ExamDay.id)
                .where(
                    ExamSlot.round_candidate_id == result.round_candidate_id,
                    ExamDay.status == "completed",
                )
            )
            is not None
        )

    def _assert_model_applicable(
        self, session: Session, exam_round: ExamRound, model: AssessmentModelVersion
    ) -> None:
        committee = session.get(Committee, exam_round.committee_id)
        if committee is None or committee.occupation != model.occupation:
            raise ValueError("Die Modellversion passt nicht zum Ausbildungsberuf des Ausschusses")
        if committee.ihk != model.ihk:
            raise ValueError("Die Modellversion passt nicht zur zuständigen IHK des Ausschusses")
        effective = self._round_effective_date(session, exam_round)
        if effective < date.fromisoformat(model.valid_from) or (
            model.valid_until is not None and effective > date.fromisoformat(model.valid_until)
        ):
            raise ValueError("Die Modellversion ist für die Prüfungsrunde nicht gültig")
        specializations = set(
            session.scalars(
                select(Candidate.specialization)
                .join(RoundCandidate, RoundCandidate.candidate_id == Candidate.id)
                .where(
                    RoundCandidate.exam_round_id == exam_round.id,
                    RoundCandidate.is_active == 1,
                )
            )
        )
        if model.specialization is not None and specializations != {model.specialization}:
            raise ValueError("Die Modellversion passt nicht zu allen Schwerpunkten der Runde")

    @staticmethod
    def _round_effective_date(session: Session, exam_round: ExamRound) -> date:
        first_day = session.scalar(
            select(func.min(ExamDay.date)).where(ExamDay.exam_round_id == exam_round.id)
        )
        if first_day:
            return date.fromisoformat(str(first_day)[:10])
        half_year = exam_round.exam_half_year_id
        from .models import ExamHalfYear

        period = session.get(ExamHalfYear, half_year)
        month = 10 if period.season == "winter" else 4
        return date(period.year, month, 1)

    @staticmethod
    def _round_has_assessment_inputs(session: Session, round_id: int) -> bool:
        result_ids = (
            select(ExamResult.id)
            .join(RoundCandidate, RoundCandidate.id == ExamResult.round_candidate_id)
            .where(RoundCandidate.exam_round_id == round_id)
        )
        tables = (
            IndividualAssessment,
            CommitteeAssessment,
            ExternalExamResult,
            ResultCalculation,
            ResultDetermination,
        )
        return any(
            session.scalar(
                select(func.count()).select_from(table).where(table.exam_result_id.in_(result_ids))
            )
            for table in tables
        )

    @staticmethod
    def _ensure_round_results(session: Session, round_id: int) -> None:
        round_candidates = list(
            session.scalars(
                select(RoundCandidate).where(
                    RoundCandidate.exam_round_id == round_id,
                    RoundCandidate.is_active == 1,
                )
            )
        )
        existing = {
            item.round_candidate_id: item
            for item in session.scalars(
                select(ExamResult).where(
                    ExamResult.round_candidate_id.in_([item.id for item in round_candidates])
                )
            )
        }
        created_at = _now()
        for round_candidate in round_candidates:
            if round_candidate.id not in existing:
                session.add(
                    ExamResult(
                        round_candidate_id=round_candidate.id,
                        current_state="incomplete",
                        correction_open=0,
                        version=1,
                        source="application",
                        created_at=created_at,
                        updated_at=created_at,
                    )
                )

    def _validate_rules(self, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise ValueError("rules muss ein Objekt sein")
        required = {"components", "external_areas", "rounding", "grades", "passing", "quorum"}
        if set(raw) != required:
            raise ValueError("Die Rechenregeln sind unvollständig oder enthalten unbekannte Felder")
        components = raw["components"]
        external_areas = raw["external_areas"]
        if not isinstance(components, list) or not components:
            raise ValueError("Mindestens eine bewertete Komponente ist erforderlich")
        if not isinstance(external_areas, list):
            raise ValueError("external_areas muss eine Liste sein")
        normalized_components = []
        keys: set[str] = set()
        component_keys: set[str] = set()
        for component in components:
            if not isinstance(component, dict) or set(component) != COMPONENT_FIELDS:
                raise ValueError("Eine Komponente ist unvollständig oder enthält unbekannte Felder")
            key = self._required_text(component.get("key"), "component key", 100)
            if key in keys:
                raise ValueError("Komponentenschlüssel müssen eindeutig sein")
            keys.add(key)
            component_keys.add(key)
            mode = component.get("mode")
            if mode not in MODEL_MODES:
                raise ValueError("Unbekanntes Bewertungsverfahren")
            criteria = component.get("criteria")
            if not isinstance(criteria, list) or not criteria:
                raise ValueError("Eine Komponente benötigt Kriterien")
            normalized_criteria = []
            criterion_keys: set[str] = set()
            for criterion in criteria:
                if not isinstance(criterion, dict) or set(criterion) != CRITERION_FIELDS:
                    raise ValueError(
                        "Ein Kriterium ist unvollständig oder enthält unbekannte Felder"
                    )
                criterion_key = self._required_text(criterion.get("key"), "criterion key", 100)
                if criterion_key in criterion_keys:
                    raise ValueError("Kriterienschlüssel müssen eindeutig sein")
                criterion_keys.add(criterion_key)
                raw_min = self._decimal(criterion.get("raw_min"), "raw_min")
                raw_max = self._decimal(criterion.get("raw_max"), "raw_max")
                if raw_max <= raw_min:
                    raise ValueError("Eine Rohpunkteskala benötigt ein echtes Intervall")
                normalized_criteria.append(
                    {
                        "key": criterion_key,
                        "label": self._required_text(criterion.get("label"), "label", 300),
                        "raw_min": _decimal_text(raw_min),
                        "raw_max": _decimal_text(raw_max),
                        "weight": _decimal_text(
                            self._percentage(criterion.get("weight"), "criterion weight")
                        ),
                    }
                )
            self._assert_weight_sum(
                [Decimal(item["weight"]) for item in normalized_criteria], "Kriterien"
            )
            required_assessors = self._integer(
                component.get("required_assessors"), "required_assessors", 1
            )
            day_scoped = component.get("day_scoped")
            additional = component.get("additional_assessor_on_deviation")
            if not isinstance(day_scoped, bool) or not isinstance(additional, bool):
                raise ValueError("day_scoped und additional_assessor_on_deviation sind boolesch")
            max_deviation = self._percentage(
                component.get("max_deviation"), "max_deviation", allow_zero=True
            )
            normalized_components.append(
                {
                    "key": key,
                    "label": self._required_text(component.get("label"), "label", 300),
                    "mode": mode,
                    "weight": _decimal_text(
                        self._percentage(component.get("weight"), "component weight")
                    ),
                    "day_scoped": day_scoped,
                    "required_assessors": required_assessors,
                    "max_deviation": _decimal_text(max_deviation),
                    "additional_assessor_on_deviation": additional,
                    "criteria": normalized_criteria,
                }
            )
        normalized_external = []
        external_keys: set[str] = set()
        for area in external_areas:
            if not isinstance(area, dict) or set(area) != EXTERNAL_AREA_FIELDS:
                raise ValueError("Ein externer Prüfungsbereich ist unvollständig")
            key = self._required_text(area.get("key"), "external area key", 100)
            if key in keys:
                raise ValueError("Prüfungsbereichsschlüssel müssen eindeutig sein")
            keys.add(key)
            external_keys.add(key)
            required_area = area.get("required")
            if not isinstance(required_area, bool):
                raise ValueError("required muss ein boolescher Wert sein")
            normalized_external.append(
                {
                    "key": key,
                    "label": self._required_text(area.get("label"), "label", 300),
                    "weight": _decimal_text(
                        self._percentage(area.get("weight"), "external weight", allow_zero=True)
                    ),
                    "required": required_area,
                }
            )
        self._assert_weight_sum(
            [Decimal(item["weight"]) for item in normalized_components]
            + [Decimal(item["weight"]) for item in normalized_external],
            "Komponenten und Prüfungsbereiche",
        )
        rounding = self._validate_rounding(raw["rounding"])
        grades = self._validate_grades(raw["grades"])
        passing = self._validate_passing(raw["passing"], component_keys, external_keys)
        quorum = self._validate_quorum(raw["quorum"])
        return {
            "components": normalized_components,
            "external_areas": normalized_external,
            "rounding": rounding,
            "grades": grades,
            "passing": passing,
            "quorum": quorum,
        }

    def _validate_rounding(self, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict) or set(raw) != {
            "intermediate",
            "overall",
            "threshold_basis",
        }:
            raise ValueError("Die Rundungsregel ist unvollständig")
        threshold_basis = raw["threshold_basis"]
        if threshold_basis not in {"unrounded", "rounded"}:
            raise ValueError("Unbekannte Grundlage für Bestehensgrenzen")
        return {
            "intermediate": self._rounding_stage(raw["intermediate"]),
            "overall": self._rounding_stage(raw["overall"]),
            "threshold_basis": threshold_basis,
        }

    def _rounding_stage(self, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict) or set(raw) != {"mode", "digits"}:
            raise ValueError("Eine Rundungsstufe ist unvollständig")
        mode = raw["mode"]
        digits = raw["digits"]
        if mode not in {"none", "half_up"}:
            raise ValueError("Unbekanntes Rundungsverfahren")
        if mode == "none":
            if digits is not None:
                raise ValueError("Ohne Rundung dürfen keine Nachkommastellen angegeben werden")
            return {"mode": mode, "digits": None}
        return {"mode": mode, "digits": self._integer(digits, "digits", 0, maximum=6)}

    def _validate_grades(self, raw: Any) -> list[dict[str, Any]]:
        if not isinstance(raw, list) or not raw:
            raise ValueError("Mindestens eine Notenzuordnung ist erforderlich")
        grades = []
        previous = Decimal(101)
        for item in raw:
            if not isinstance(item, dict) or set(item) != {"label", "min_points"}:
                raise ValueError("Eine Notenzuordnung ist unvollständig")
            minimum = self._points(item["min_points"], "min_points")
            if minimum >= previous:
                raise ValueError("Notengrenzen müssen streng absteigend sortiert sein")
            previous = minimum
            grades.append(
                {
                    "label": self._required_text(item["label"], "grade label", 100),
                    "min_points": _decimal_text(minimum),
                }
            )
        if Decimal(grades[-1]["min_points"]) != 0:
            raise ValueError("Die Notenzuordnung muss die gesamte Skala bis 0 abdecken")
        return grades

    def _validate_passing(
        self, raw: Any, component_keys: set[str], external_keys: set[str]
    ) -> dict[str, Any]:
        if not isinstance(raw, dict) or set(raw) != {
            "overall_min",
            "component_minima",
            "external_minima",
        }:
            raise ValueError("Die Bestehensregeln sind unvollständig")
        component_minima = raw["component_minima"]
        external_minima = raw["external_minima"]
        if not isinstance(component_minima, dict) or not isinstance(external_minima, dict):
            raise ValueError("Teilbestehensgrenzen müssen Objekte sein")
        if set(component_minima) - component_keys or set(external_minima) - external_keys:
            raise ValueError("Eine Bestehensgrenze verweist auf einen unbekannten Bereich")
        return {
            "overall_min": _decimal_text(self._points(raw["overall_min"], "overall_min")),
            "component_minima": {
                key: _decimal_text(self._points(value, key))
                for key, value in component_minima.items()
            },
            "external_minima": {
                key: _decimal_text(self._points(value, key))
                for key, value in external_minima.items()
            },
        }

    def _validate_quorum(self, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict) or set(raw) != {"minimum_members", "majority"}:
            raise ValueError("Die Beschlussregel ist unvollständig")
        if raw["majority"] != "simple":
            raise ValueError("Aktuell wird nur die einfache Mehrheit unterstützt")
        return {
            "minimum_members": self._integer(raw["minimum_members"], "minimum_members", 1),
            "majority": "simple",
        }

    @staticmethod
    def _assert_weight_sum(weights: list[Decimal], level: str) -> None:
        if sum(weights, Decimal(0)) != Decimal(100):
            raise ValueError(f"Direkte Gewichte der Ebene {level} müssen 100 Prozent ergeben")

    def _assert_quorum(
        self, rules: dict[str, Any], participants: set[int], actual: set[int]
    ) -> None:
        if not participants or not participants.issubset(actual):
            raise ValueError("Nur tatsächlich mitwirkende Prüfer dürfen beschließen")
        if len(participants) < int(rules["quorum"]["minimum_members"]):
            raise ValueError("Das Gremium ist nicht ordnungsgemäß besetzt")

    def _validate_vote(self, raw: Any, participants: set[int]) -> dict[str, list[int]]:
        if not isinstance(raw, dict) or set(raw) != {"yes", "no", "abstain"}:
            raise ValueError("Das Abstimmungsergebnis ist unvollständig")
        vote = {key: sorted(self._participant_set(raw[key])) for key in raw}
        all_voters = set(vote["yes"]) | set(vote["no"]) | set(vote["abstain"])
        if all_voters != participants or sum(len(value) for value in vote.values()) != len(
            participants
        ):
            raise ValueError("Jedes mitwirkende Mitglied benötigt genau eine Stimme")
        if len(vote["yes"]) <= len(vote["no"]):
            raise ValueError("Der Beschluss hat keine Mehrheit")
        return vote

    def _validate_dissent(self, raw: Any, participants: set[int]) -> list[dict[str, Any]]:
        if not isinstance(raw, list):
            raise ValueError("Abweichende Voten müssen als Liste übermittelt werden")
        dissent = []
        for item in raw:
            if not isinstance(item, dict) or set(item) != {"member_id", "statement"}:
                raise ValueError("Ein abweichendes Votum ist unvollständig")
            member_id = self._integer(item["member_id"], "member_id", 1)
            if member_id not in participants:
                raise ValueError("Ein abweichendes Votum gehört nicht zum beschließenden Gremium")
            dissent.append(
                {
                    "member_id": member_id,
                    "statement": self._required_text(item["statement"], "statement", 3000),
                }
            )
        return dissent

    @staticmethod
    def _participant_set(raw: Any) -> set[int]:
        if not isinstance(raw, list) or any(
            not isinstance(item, int) or isinstance(item, bool) or item < 1 for item in raw
        ):
            raise ValueError("participant_member_ids muss eine Liste gültiger IDs sein")
        if len(set(raw)) != len(raw):
            raise ValueError("Mitwirkende dürfen nicht doppelt angegeben werden")
        return set(raw)

    @staticmethod
    def _component(rules: dict[str, Any], key: str) -> dict[str, Any]:
        component = next((item for item in rules["components"] if item["key"] == key), None)
        if component is None:
            raise ValueError("Unbekannte Bewertungskomponente")
        return component

    @staticmethod
    def _criterion(component: dict[str, Any], key: str) -> dict[str, Any]:
        criterion = next((item for item in component["criteria"] if item["key"] == key), None)
        if criterion is None:
            raise ValueError("Unbekanntes Bewertungskriterium")
        return criterion

    @staticmethod
    def _external_area(rules: dict[str, Any], key: str) -> dict[str, Any]:
        area = next((item for item in rules["external_areas"] if item["key"] == key), None)
        if area is None:
            raise ValueError("Unbekannter externer Prüfungsbereich")
        return area

    @staticmethod
    def _round(value: Decimal, rule: dict[str, Any]) -> Decimal:
        if rule["mode"] == "none":
            return value
        quantum = Decimal(1).scaleb(-int(rule["digits"]))
        return value.quantize(quantum, rounding=ROUND_HALF_UP)

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _required_result_version(payload: dict[str, Any]) -> int:
        value = payload.get("version")
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError("Eine gültige Ergebnisversion ist erforderlich")
        return value

    @staticmethod
    def _integer(value: Any, field: str, minimum: int, maximum: int | None = None) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            raise ValueError(f"{field} muss eine ganze Zahl ab {minimum} sein")
        if maximum is not None and value > maximum:
            raise ValueError(f"{field} darf höchstens {maximum} sein")
        return value

    @staticmethod
    def _decimal(value: Any, field: str) -> Decimal:
        if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
            raise ValueError(f"{field} muss eine Zahl sein")
        try:
            result = Decimal(str(value))
        except InvalidOperation as error:
            raise ValueError(f"{field} muss eine Zahl sein") from error
        if not result.is_finite():
            raise ValueError(f"{field} muss endlich sein")
        return result

    def _points(self, value: Any, field: str) -> Decimal:
        points = self._decimal(value, field)
        if points < 0 or points > 100:
            raise ValueError(f"{field} muss zwischen 0 und 100 liegen")
        return points

    def _percentage(self, value: Any, field: str, *, allow_zero: bool = False) -> Decimal:
        percentage = self._decimal(value, field)
        minimum = 0 if allow_zero else Decimal("0.0000001")
        if percentage < minimum or percentage > 100:
            raise ValueError(f"{field} muss zwischen {minimum} und 100 liegen")
        return percentage

    @staticmethod
    def _required_text(value: Any, field: str, maximum: int) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} ist erforderlich")
        normalized = value.strip()
        if len(normalized) > maximum:
            raise ValueError(f"{field} ist zu lang")
        return normalized

    @staticmethod
    def _optional_text(value: Any, maximum: int) -> str | None:
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            raise ValueError("Textwert erwartet")
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > maximum:
            raise ValueError("Textwert ist zu lang")
        return normalized

    @staticmethod
    def _required_date(value: Any, field: str) -> date:
        if not isinstance(value, str):
            raise ValueError(f"{field} muss ein Datum sein")
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise ValueError(f"{field} muss ein ISO-Datum sein") from error

    def _optional_date(self, value: Any, field: str) -> date | None:
        if value is None or value == "":
            return None
        return self._required_date(value, field)

    @staticmethod
    def _required_datetime(value: Any, field: str) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{field} muss ein Zeitpunkt sein")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as error:
            raise ValueError(f"{field} muss ein ISO-Zeitpunkt sein") from error
        if parsed.tzinfo is None:
            raise ValueError(f"{field} benötigt eine Zeitzone")
        return parsed.isoformat()

    @staticmethod
    def _add_years(value: date, years: int) -> date:
        try:
            return value.replace(year=value.year + years)
        except ValueError:
            return value.replace(month=2, day=28, year=value.year + years)

    @staticmethod
    def _model_view(model: AssessmentModelVersion) -> dict[str, Any]:
        return {
            "id": model.id,
            "model_key": model.model_key,
            "version": model.version,
            "ihk": model.ihk,
            "occupation": model.occupation,
            "specialization": model.specialization,
            "training_regulation": model.training_regulation,
            "exam_regulation": model.exam_regulation,
            "ihk_guidelines": model.ihk_guidelines,
            "valid_from": model.valid_from,
            "valid_until": model.valid_until,
            "official_scale": {
                "min": model.official_scale_min,
                "max": model.official_scale_max,
            },
            "rules": json.loads(model.rules_json),
            "retention_rule_reference": model.retention_rule_reference,
            "retention_years": model.retention_years,
            "created_by_member_id": model.created_by_member_id,
            "created_at": model.created_at,
        }

    def _binding_view(
        self, binding: ExamRoundAssessmentBinding, model: AssessmentModelVersion
    ) -> dict[str, Any]:
        return {
            "id": binding.id,
            "exam_round_id": binding.exam_round_id,
            "assessment_model_version_id": binding.assessment_model_version_id,
            "version": binding.version,
            "bound_by_member_id": binding.bound_by_member_id,
            "binding_reason": binding.binding_reason,
            "bound_at": binding.bound_at,
            "model": {
                "model_key": model.model_key,
                "version": model.version,
                "ihk": model.ihk,
                "occupation": model.occupation,
                "specialization": model.specialization,
                "valid_from": model.valid_from,
                "valid_until": model.valid_until,
            },
        }

    @staticmethod
    def _individual_view(item: IndividualAssessment) -> dict[str, Any]:
        return {
            "id": item.id,
            "component_key": item.component_key,
            "criterion_key": item.criterion_key,
            "assessor_member_id": item.assessor_member_id,
            "revision": item.revision,
            "raw_points": item.raw_points,
            "normalized_points": item.normalized_points,
            "rationale": item.rationale,
            "status": item.status,
            "previous_assessment_id": item.previous_assessment_id,
            "change_reason": item.change_reason,
            "submitted_at": item.submitted_at,
            "created_at": item.created_at,
        }

    def _individual_counts(self, session: Session, result_id: int) -> list[dict[str, Any]]:
        counts: dict[str, dict[str, int]] = {}
        for item in self._current_individuals(session, result_id):
            component = counts.setdefault(item.component_key, {"draft": 0, "submitted": 0})
            if item.status in component:
                component[item.status] += 1
        return [{"component_key": key, **value} for key, value in sorted(counts.items())]

    @staticmethod
    def _committee_view(item: CommitteeAssessment) -> dict[str, Any]:
        return {
            "id": item.id,
            "component_key": item.component_key,
            "revision": item.revision,
            "points": item.points,
            "rationale": item.rationale,
            "participant_member_ids": json.loads(item.participant_member_ids_json),
            "vote": json.loads(item.vote_json),
            "dissent": json.loads(item.dissent_json),
            "status": item.status,
            "previous_assessment_id": item.previous_assessment_id,
            "determined_by_member_id": item.determined_by_member_id,
            "determined_at": item.determined_at,
        }

    @staticmethod
    def _external_view(item: ExternalExamResult) -> dict[str, Any]:
        return {
            "id": item.id,
            "area_key": item.area_key,
            "revision": item.revision,
            "points": item.points,
            "grade": item.grade,
            "professional_status": item.professional_status,
            "determining_authority": item.determining_authority,
            "source_reference": item.source_reference,
            "status": item.status,
            "recorded_by_member_id": item.recorded_by_member_id,
            "recorded_at": item.recorded_at,
            "confirmed_by_member_id": item.confirmed_by_member_id,
            "confirmed_at": item.confirmed_at,
            "previous_external_result_id": item.previous_external_result_id,
            "correction_reason": item.correction_reason,
        }

    @staticmethod
    def _calculation_view(item: ResultCalculation) -> dict[str, Any]:
        return {
            "id": item.id,
            "version": item.version,
            "input_fingerprint": item.input_fingerprint,
            "total_points": item.total_points,
            "grade": item.grade,
            "passed": bool(item.passed),
            "path": json.loads(item.calculation_path_json),
            "created_at": item.created_at,
        }

    def _determination_view(self, session: Session, item: ResultDetermination) -> dict[str, Any]:
        return {
            "id": item.id,
            "revision": item.revision,
            "result_calculation_id": item.result_calculation_id,
            "participant_member_ids": json.loads(item.participant_member_ids_json),
            "vote": json.loads(item.vote_json),
            "dissent": json.loads(item.dissent_json),
            "status": item.status,
            "previous_determination_id": item.previous_determination_id,
            "correction_id": item.correction_id,
            "determined_by_member_id": item.determined_by_member_id,
            "determined_at": item.determined_at,
            "confirmation_member_ids": sorted(self._confirmation_ids(session, item.id)),
        }

    @staticmethod
    def _correction_view(item: ResultCorrection) -> dict[str, Any]:
        return {
            "id": item.id,
            "result_determination_id": item.result_determination_id,
            "reason": item.reason,
            "requested_by_member_id": item.requested_by_member_id,
            "status": item.status,
            "reopening_reference": item.reopening_reference,
            "requested_at": item.requested_at,
            "completed_at": item.completed_at,
        }

    @staticmethod
    def _communication_view(item: ResultCommunication) -> dict[str, Any]:
        return {
            "id": item.id,
            "result_determination_id": item.result_determination_id,
            "method": item.method,
            "responsible_member_id": item.responsible_member_id,
            "communicated_at": item.communicated_at,
            "external_document_status": item.external_document_status,
            "external_document_reference": item.external_document_reference,
            "status": item.status,
            "created_at": item.created_at,
        }

    @staticmethod
    def _retention_view(item: ResultRetention) -> dict[str, Any]:
        return {
            "rule_reference": item.rule_reference,
            "period_start": item.period_start,
            "retain_until": item.retain_until,
            "legal_hold": bool(item.legal_hold),
            "hold_reason": item.hold_reason,
            "updated_by_member_id": item.updated_by_member_id,
            "updated_at": item.updated_at,
        }

    @staticmethod
    def _export_view(item: ResultExport) -> dict[str, Any]:
        return {
            "id": item.id,
            "result_determination_id": item.result_determination_id,
            "export_kind": item.export_kind,
            "status": item.status,
            "generated_by_member_id": item.generated_by_member_id,
            "generated_at": item.generated_at,
        }
