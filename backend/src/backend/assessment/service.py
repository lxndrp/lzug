"""Assessment-owned result rules and use cases over materialized value ports."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from backend.assessment.ports import (
    AssessmentActorSnapshot,
    AssessmentHumanExportData,
    AssessmentMachineExportData,
    AssessmentModelCommand,
    AssessmentModelSnapshot,
    AssessmentResultSnapshot,
    AssessmentUnitOfWorkFactory,
    CalculationCommand,
    IndividualAssessmentCommand,
    RoundBindingCommand,
)
from backend.assessment.rules import AssessmentRules
from backend.errors import AssessmentWriteConflictError

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
RETENTION_FIELDS = {
    "version",
    "period_start",
    "retain_until",
    "legal_hold",
    "hold_reason",
    "release_reason",
}
RESULT_STATES = {"incomplete", "calculation_ready", "determined", "communicated"}
HISTORY_STATUSES = {"current", "superseded"}


ExamResultConflictError = AssessmentWriteConflictError


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _decimal_text(value: Decimal) -> str:
    normalized = format(value, "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


class ExamResultService:
    """Enforce result rules and disclosure over Assessment-owned snapshots."""

    def __init__(self, unit_of_work_factory: AssessmentUnitOfWorkFactory | None = None):
        self._unit_of_work_factory = unit_of_work_factory

    def list_models(self, actor: AssessmentActorSnapshot) -> dict[str, Any]:
        if not actor["member_ids"]:
            raise PermissionError("Forbidden.")
        with self._unit_of_work_factory() as work:
            models = work.queries.list_models()
            return {"items": [self._model_view(item) for item in models]}

    def create_model(
        self, actor: AssessmentActorSnapshot, payload: dict[str, Any]
    ) -> dict[str, Any]:
        if not actor["management_committee_ids"]:
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
        member_ids = actor["member_ids"]
        member_id = min(member_ids)
        command: AssessmentModelCommand = {
            "model_key": self._required_text(payload.get("model_key"), "model_key", 100),
            "version": self._integer(payload.get("version"), "version", 1),
            "ihk": self._required_text(payload.get("ihk"), "ihk", 300),
            "occupation": self._required_text(payload.get("occupation"), "occupation", 300),
            "specialization": self._optional_text(payload.get("specialization"), 300),
            "training_regulation": self._required_text(
                payload.get("training_regulation"), "training_regulation", 1000
            ),
            "exam_regulation": self._required_text(
                payload.get("exam_regulation"), "exam_regulation", 1000
            ),
            "ihk_guidelines": self._required_text(
                payload.get("ihk_guidelines"), "ihk_guidelines", 2000
            ),
            "valid_from": valid_from.isoformat(),
            "valid_until": valid_until.isoformat() if valid_until else None,
            "official_scale_min": _decimal_text(official_min),
            "official_scale_max": _decimal_text(official_max),
            "rules": rules,
            "retention_rule_reference": self._required_text(
                payload.get("retention_rule_reference"), "retention_rule_reference", 1000
            ),
            "retention_years": retention_years,
            "actor_member_id": member_id,
        }
        with self._unit_of_work_factory(write=True) as work:
            model = work.repository.create_model(command)
            return self._model_view(model)

    def get_round_binding(
        self, actor: AssessmentActorSnapshot, round_id: int
    ) -> dict[str, Any] | None:
        with self._unit_of_work_factory() as work:
            planning = work.queries.planning_for_round(round_id)
            if planning is None:
                return None
            if not self._can_read_committee(actor, planning["committee_id"]):
                raise PermissionError("Forbidden.")
            binding = work.queries.binding_for_round(round_id)
            if binding is None:
                return None
            model = work.queries.model_by_id(binding["model_version_id"])
            if model is None:  # pragma: no cover - protected by the database constraint
                raise RuntimeError("Gebundene Bewertungsmodellversion fehlt")
            return self._binding_view(binding, model)

    def bind_round(
        self, actor: AssessmentActorSnapshot, round_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        model_id = self._integer(payload.get("assessment_model_version_id"), "model version", 1)
        reason = self._required_text(payload.get("reason"), "reason", 1000)
        expected = (
            self._integer(payload.get("version"), "binding version", 1)
            if payload.get("version") is not None
            else None
        )
        with self._unit_of_work_factory(write=True) as work:
            planning = work.queries.planning_for_round(round_id)
            if planning is None:
                raise ValueError("Prüfungsrunde nicht gefunden")
            committee_id = planning["committee_id"]
            actor_id = actor["member_by_committee"].get(committee_id)
            if actor_id is None or not self._can_manage_committee(actor, committee_id):
                raise PermissionError("Forbidden.")
            identity = work.queries.identity_for_committee(committee_id)
            model = work.queries.model_by_id(model_id)
            if model is None:
                raise ValueError("Bewertungsmodellversion nicht gefunden")
            self._assert_model_applicable(planning, identity, model)
            binding = work.queries.binding_for_round(round_id)
            if binding is not None:
                if binding["model_version_id"] == model["id"]:
                    return self._binding_view(binding, model)
                if expected is None or binding["version"] != expected:
                    raise ExamResultConflictError(
                        "Die Modellbindung wurde zwischenzeitlich geändert"
                    )
                if work.queries.round_has_assessment_inputs(round_id):
                    raise ExamResultConflictError(
                        "Nach der ersten Bewertung kann die Modellversion nicht neu gebunden werden"
                    )
            command: RoundBindingCommand = {
                "round_id": round_id,
                "model_version_id": model["id"],
                "expected_binding_version": binding["version"] if binding is not None else None,
                "actor_member_id": actor_id,
                "reason": reason,
                "bound_at": _now(),
            }
            work.repository.bind_round(command)
            current = work.queries.binding_for_round(round_id)
            if current is None:  # pragma: no cover - adapter contract
                raise RuntimeError("Die Bewertungsmodellbindung wurde nicht gespeichert")
            work.repository.ensure_round_results(
                {"round_id": round_id, "expected_binding_version": current["version"]}
            )
            return self._binding_view(current, model)

    def get_by_slot(
        self,
        actor: AssessmentActorSnapshot,
        slot_id: int,
        day_id: int | None = None,
    ) -> dict[str, Any] | None:
        return self._read_result(actor, lambda queries: queries.result_by_slot(slot_id, day_id))

    def get(self, actor: AssessmentActorSnapshot, result_id: int) -> dict[str, Any] | None:
        return self._read_result(actor, lambda queries: queries.result_by_id(result_id))

    def _read_result(self, actor, lookup):
        with self._unit_of_work_factory(write=False) as work:
            result = lookup(work.queries)
            if result is None:
                return None
            self._assert_projection_access(result, actor)
            if self._calculation_command(result) is None:
                return self._project_and_materialize(work, result, actor)

        with self._unit_of_work_factory(write=True) as work:
            result = lookup(work.queries)
            if result is None:
                return None
            self._assert_projection_access(result, actor)
            result = self._ensure_calculation(work, result)
            return self._project_and_materialize(work, result, actor)

    def save_individual(
        self, actor: AssessmentActorSnapshot, result_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        expected = self._required_result_version(payload)
        component_key = self._required_text(payload.get("component_key"), "component_key", 100)
        criterion_key = self._required_text(payload.get("criterion_key"), "criterion_key", 100)
        submitted = payload.get("submitted", False)
        if not isinstance(submitted, bool):
            raise ValueError("submitted muss ein boolescher Wert sein")
        with self._unit_of_work_factory(write=True) as work:
            result = self._required_access(work, actor, result_id)
            member_id = actor["member_by_committee"].get(result["committee_id"])
            if member_id not in result["participant_member_ids"]:
                raise PermissionError("Forbidden.")
            component = self._component(result["model"]["rules"], component_key)
            criterion = self._criterion(component, criterion_key)
            raw_points = self._decimal(payload.get("raw_points"), "raw_points")
            raw_min, raw_max = (
                Decimal(str(criterion["raw_min"])),
                Decimal(str(criterion["raw_max"])),
            )
            if raw_points < raw_min or raw_points > raw_max:
                raise ValueError("Rohpunkte liegen außerhalb der gebundenen Kriterienskala")
            normalized = (raw_points - raw_min) * Decimal(100) / (raw_max - raw_min)
            rationale = self._optional_text(payload.get("rationale"), 4000)
            change_reason = self._optional_text(payload.get("change_reason"), 2000)
            current = self._latest_individual(
                result["individual_assessments"], component_key, criterion_key, member_id
            )
            status = "submitted" if submitted else "draft"
            if (
                current
                and Decimal(current["raw_points"]) == raw_points
                and Decimal(current["normalized_points"]) == normalized
                and current["rationale"] == rationale
                and current["status"] == status
            ):
                return self._project_and_materialize(work, result, actor)
            self._assert_inputs_mutable(result)
            disclosed = component_key in {x["component_key"] for x in result["disclosures"]}
            if (disclosed or result["correction_open"]) and change_reason is None:
                raise ValueError("Eine Änderung nach Offenlegung benötigt eine Begründung")
            command: IndividualAssessmentCommand = {
                "result_id": result_id,
                "expected_result_version": expected,
                "component_key": component_key,
                "criterion_key": criterion_key,
                "assessor_member_id": member_id,
                "raw_points": _decimal_text(raw_points),
                "normalized_points": _decimal_text(normalized),
                "rationale": rationale,
                "status": status,
                "previous_assessment_id": current["id"] if current else None,
                "change_reason": change_reason,
                "submitted_at": _now() if submitted else None,
                "created_at": _now(),
            }
            work.repository.save_individual_assessment(command)
            work.repository.complete_result_day_mutation(
                result_id, "result_assessment", payload, member_id, change_reason
            )
            updated = work.queries.result_by_id(result_id)
            assert updated is not None
            updated = self._ensure_calculation(work, updated)
            return self._project_and_materialize(work, updated, actor)

    def withdraw_individual(
        self,
        actor: AssessmentActorSnapshot,
        result_id: int,
        assessment_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        expected = self._required_result_version(payload)
        reason = self._required_text(payload.get("reason"), "reason", 2000)
        with self._unit_of_work_factory(write=True) as work:
            result = self._required_access(work, actor, result_id)
            member_id = actor["member_by_committee"].get(result["committee_id"])
            item = next(
                (x for x in result["individual_assessments"] if x["id"] == assessment_id), None
            )
            if (
                item is None
                or item["assessor_member_id"] != member_id
                or member_id not in result["participant_member_ids"]
                or item["status"] not in {"draft", "submitted"}
            ):
                raise PermissionError("Forbidden.")
            if item["component_key"] in {x["component_key"] for x in result["disclosures"]}:
                raise ExamResultConflictError(
                    "Nach Offenlegung kann eine Bewertung nur begründet revidiert werden"
                )
            self._assert_inputs_mutable(result)
            command: IndividualAssessmentCommand = {
                "result_id": result_id,
                "expected_result_version": expected,
                "component_key": item["component_key"],
                "criterion_key": item["criterion_key"],
                "assessor_member_id": member_id,
                "raw_points": item["raw_points"],
                "normalized_points": item["normalized_points"],
                "rationale": item["rationale"],
                "status": "withdrawn",
                "previous_assessment_id": item["id"],
                "change_reason": reason,
                "submitted_at": None,
                "created_at": _now(),
            }
            work.repository.save_individual_assessment(command)
            work.repository.complete_result_day_mutation(
                result_id, "result_assessment", payload, member_id, reason
            )
            updated = work.queries.result_by_id(result_id)
            assert updated is not None
            updated = self._ensure_calculation(work, updated)
            return self._project_and_materialize(work, updated, actor)

    def disclose(
        self, actor: AssessmentActorSnapshot, result_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        expected = self._required_result_version(payload)
        component_key = self._required_text(payload.get("component_key"), "component_key", 100)
        with self._unit_of_work_factory(write=True) as work:
            result = self._required_access(work, actor, result_id)
            committee = result["committee_id"]
            member_id = actor["member_by_committee"].get(committee)
            rules = result["model"]["rules"]
            component = self._component(rules, component_key)
            if component_key in {x["component_key"] for x in result["disclosures"]}:
                return self._project_and_materialize(work, result, actor)
            if member_id not in result["participant_member_ids"] or not self._can_manage_committee(
                actor, committee
            ):
                raise PermissionError("Forbidden.")
            self._assert_inputs_mutable(result)
            if component["mode"] == "committee":
                complete = self._individual_component_complete(
                    result, component, set(result["participant_member_ids"])
                )
            else:
                complete = self._component_score(result, component, strict=True) is not None
            if not complete:
                raise ValueError("Die vorgeschriebenen individuellen Beiträge fehlen")
            work.repository.disclose_component(
                {
                    "result_id": result_id,
                    "expected_result_version": expected,
                    "component_key": component_key,
                    "disclosed_by_member_id": member_id,
                    "disclosed_at": _now(),
                }
            )
            work.repository.complete_result_day_mutation(
                result_id, "result_disclosure", payload, member_id
            )
            updated = work.queries.result_by_id(result_id)
            assert updated is not None
            return self._project_and_materialize(work, updated, actor)

    def determine_component(self, actor, result_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        expected = self._required_result_version(payload)
        key = self._required_text(payload.get("component_key"), "component_key", 100)
        points = self._decimal(payload.get("points"), "points")
        if points < 0 or points > 100:
            raise ValueError("points muss zwischen 0 und 100 liegen")
        rationale = self._optional_text(payload.get("rationale"), 4000)
        with self._unit_of_work_factory(write=True) as work:
            result = self._required_access(work, actor, result_id)
            member_id = actor["member_by_committee"].get(result["committee_id"])
            actual = set(result["participant_member_ids"])
            rules = result["model"]["rules"]
            component = self._component(rules, key)
            if component["mode"] != "committee":
                raise ValueError("Diese Komponente verwendet unabhängige Mehrfachbewertung")
            if member_id not in actual or not self._can_manage_committee(
                actor, result["committee_id"]
            ):
                raise PermissionError("Forbidden.")
            if key not in {x["component_key"] for x in result["disclosures"]}:
                raise ValueError("Die individuellen Bewertungen sind noch nicht offengelegt")
            chosen = self._participant_set(payload.get("participant_member_ids"))
            self._assert_quorum(rules, chosen, actual)
            vote = self._validate_vote(payload.get("vote"), chosen)
            dissent = self._validate_dissent(payload.get("dissent", []), chosen)
            current = next(
                (
                    x
                    for x in result["component_assessments"]
                    if x["component_key"] == key and x["status"] == "current"
                ),
                None,
            )
            if current and not result["correction_open"]:
                if (
                    Decimal(current["points"]) == points
                    and current["rationale"] == rationale
                    and set(current["participant_member_ids"]) == chosen
                    and current["vote"] == vote
                    and current["dissent"] == dissent
                ):
                    return self._project_and_materialize(work, result, actor)
                raise ExamResultConflictError(
                    "Eine festgestellte Komponentenbewertung benötigt einen Korrekturvorgang"
                )
            self._assert_inputs_mutable(result)
            individual_points = [
                Decimal(x["normalized_points"])
                for x in self._current_individuals(result)
                if x["component_key"] == key and x["status"] == "submitted"
            ]
            if (
                individual_points
                and (points < min(individual_points) or points > max(individual_points))
                and rationale is None
            ):
                raise ValueError(
                    "Eine gemeinsame Bewertung außerhalb der Einzelspanne benötigt eine Begründung"
                )
            work.repository.determine_component(
                {
                    "result_id": result_id,
                    "expected_result_version": expected,
                    "component_key": key,
                    "revision": 1 if current is None else current["revision"] + 1,
                    "points": _decimal_text(points),
                    "rationale": rationale,
                    "participant_member_ids": sorted(chosen),
                    "vote": vote,
                    "dissent": dissent,
                    "previous_assessment_id": current["id"] if current else None,
                    "determined_by_member_id": member_id,
                    "determined_at": _now(),
                }
            )
            work.repository.complete_result_day_mutation(
                result_id, "result_assessment", payload, member_id
            )
            updated = work.queries.result_by_id(result_id)
            assert updated is not None
            updated = self._ensure_calculation(work, updated)
            return self._project_and_materialize(work, updated, actor)

    def record_external(self, actor, result_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        expected = self._required_result_version(payload)
        key = self._required_text(payload.get("area_key"), "area_key", 100)
        points = self._decimal(payload.get("points"), "points")
        if points < 0 or points > 100:
            raise ValueError("points muss zwischen 0 und 100 liegen")
        grade = self._optional_text(payload.get("grade"), 100)
        status = self._required_text(payload.get("professional_status"), "professional_status", 100)
        authority = self._required_text(
            payload.get("determining_authority"), "determining_authority", 300
        )
        source = self._required_text(payload.get("source_reference"), "source_reference", 1000)
        reason = self._optional_text(payload.get("correction_reason"), 2000)
        with self._unit_of_work_factory(write=True) as work:
            result = self._required_access(work, actor, result_id)
            member_id = actor["member_by_committee"].get(result["committee_id"])
            if not self._can_manage_committee(actor, result["committee_id"]):
                raise PermissionError("Forbidden.")
            area = self._external_area(result["model"]["rules"], key)
            current = next(
                (
                    x
                    for x in reversed(result["external_results"])
                    if x["area_key"] == key and x["status"] in {"confirmed", "unconfirmed"}
                ),
                None,
            )
            if (
                current is not None
                and (current["status"] == "confirmed" or result["correction_open"])
                and reason is None
            ):
                raise ValueError("Eine Ersetzung benötigt eine Korrekturbegründung")
            self._assert_inputs_mutable(result)
            work.repository.record_external_result(
                {
                    "result_id": result_id,
                    "expected_result_version": expected,
                    "area_key": key,
                    "revision": 1 if current is None else current["revision"] + 1,
                    "points": _decimal_text(points),
                    "grade": grade,
                    "professional_status": status,
                    "determining_authority": authority,
                    "source_reference": source,
                    "recorded_by_member_id": member_id,
                    "recorded_at": _now(),
                    "previous_external_result_id": current["id"] if current else None,
                    "correction_reason": reason,
                    "result_state": (
                        result["state"]
                        if any(item["status"] == "current" for item in result["determinations"])
                        or not area["required"]
                        else "incomplete"
                    ),
                }
            )
            work.repository.complete_result_day_mutation(
                result_id, "result_external", payload, member_id, reason
            )
            updated = work.queries.result_by_id(result_id)
            assert updated is not None
            updated = self._ensure_calculation(work, updated)
            return self._project_and_materialize(work, updated, actor)

    def confirm_external(
        self, actor, result_id: int, external_result_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        expected = self._required_result_version(payload)
        with self._unit_of_work_factory(write=True) as work:
            result = self._required_access(work, actor, result_id)
            member_id = actor["member_by_committee"].get(result["committee_id"])
            if not self._can_manage_committee(actor, result["committee_id"]):
                raise PermissionError("Forbidden.")
            external = next(
                (x for x in result["external_results"] if x["id"] == external_result_id), None
            )
            if external is None or external["status"] != "unconfirmed":
                raise ValueError("External result is not confirmable")
            if external["recorded_by_member_id"] == member_id:
                raise PermissionError("Forbidden.")
            work.repository.confirm_external_result(
                {
                    "result_id": result_id,
                    "external_result_id": external_result_id,
                    "expected_result_version": expected,
                    "confirmed_by_member_id": member_id,
                    "confirmed_at": _now(),
                }
            )
            work.repository.complete_result_day_mutation(
                result_id, "result_external", payload, member_id
            )
            updated = work.queries.result_by_id(result_id)
            assert updated is not None
            updated = self._ensure_calculation(work, updated)
            return self._project_and_materialize(work, updated, actor)

    def determine_result(self, actor, result_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        expected = self._required_result_version(payload)
        with self._unit_of_work_factory(write=True) as work:
            result = self._required_access(work, actor, result_id)
            member_id = actor["member_by_committee"].get(result["committee_id"])
            actual = set(result["participant_member_ids"])
            if member_id not in actual or not self._can_manage_committee(
                actor, result["committee_id"]
            ):
                raise PermissionError("Forbidden.")
            rules = result["model"]["rules"]
            chosen = self._participant_set(payload.get("participant_member_ids"))
            self._assert_quorum(rules, chosen, actual)
            vote = self._validate_vote(payload.get("vote"), chosen)
            dissent = self._validate_dissent(payload.get("dissent", []), chosen)
            current = next((x for x in result["determinations"] if x["status"] == "current"), None)
            if current and not result["correction_open"]:
                if (
                    set(current["participant_member_ids"]) == chosen
                    and current["vote"] == vote
                    and current["dissent"] == dissent
                ):
                    return self._project_and_materialize(work, result, actor)
                raise ExamResultConflictError("Das Ergebnis wurde bereits festgestellt")
            if result["version"] != expected:
                raise ExamResultConflictError("Der Ergebnisstand wurde zwischenzeitlich geändert")
            self._assert_inputs_mutable(result)
            result = self._ensure_calculation(work, result)
            calculation = result["calculations"][-1] if result["calculations"] else None
            if calculation is None:
                raise ValueError("Das Ergebnis ist noch nicht berechnungsbereit")
            # A calculation may be materialized in this same UoW; preserve the
            # caller's version check before applying the determination command.
            current = next((x for x in result["determinations"] if x["status"] == "current"), None)
            correction = next((x for x in result["corrections"] if x["status"] == "open"), None)
            work.repository.determine_result(
                {
                    "result_id": result_id,
                    "expected_result_version": result["version"],
                    "calculation_id": calculation["id"],
                    "revision": 1 if current is None else current["revision"] + 1,
                    "participant_member_ids": sorted(chosen),
                    "vote": vote,
                    "dissent": dissent,
                    "previous_determination_id": current["id"] if current else None,
                    "correction_id": correction["id"] if correction else None,
                    "determined_by_member_id": member_id,
                    "determined_at": _now(),
                }
            )
            work.repository.complete_result_day_mutation(
                result_id, "result_determine", payload, member_id
            )
            updated = work.queries.result_by_id(result_id)
            assert updated is not None
            return self._project_and_materialize(work, updated, actor)

    def confirm_record(self, actor, result_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        expected = self._required_result_version(payload)
        with self._unit_of_work_factory(write=True) as work:
            result = self._required_access(work, actor, result_id)
            member_id = actor["member_by_committee"].get(result["committee_id"])
            determination = next(
                (x for x in result["determinations"] if x["status"] == "current"), None
            )
            if determination is None:
                raise ValueError("Es liegt noch keine Ergebnisfeststellung vor")
            if member_id not in set(determination["participant_member_ids"]):
                raise PermissionError("Forbidden.")
            if any(
                x["determination_id"] == determination["id"]
                and x["committee_member_id"] == member_id
                for x in result["record_confirmations"]
            ):
                return self._project_and_materialize(work, result, actor)
            if result["correction_open"]:
                raise ExamResultConflictError(
                    "Während einer Korrektur kann die Niederschrift nicht bestätigt werden"
                )
            work.repository.confirm_record(
                {
                    "result_id": result_id,
                    "expected_result_version": expected,
                    "determination_id": determination["id"],
                    "committee_member_id": member_id,
                    "confirmed_at": _now(),
                }
            )
            work.repository.complete_result_day_mutation(
                result_id, "result_confirm_record", payload, member_id
            )
            updated = work.queries.result_by_id(result_id)
            assert updated is not None
            return self._project_and_materialize(work, updated, actor)

    def open_correction(self, actor, result_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        expected = self._required_result_version(payload)
        reason = self._required_text(payload.get("reason"), "reason", 3000)
        reopening = self._optional_text(payload.get("reopening_reference"), 1000)
        with self._unit_of_work_factory(write=True) as work:
            result = self._required_access(work, actor, result_id)
            member_id = actor["member_by_committee"].get(result["committee_id"])
            if member_id is None or not self._can_manage_committee(actor, result["committee_id"]):
                raise PermissionError("Forbidden.")
            current = next((x for x in result["determinations"] if x["status"] == "current"), None)
            if current is None:
                raise ValueError("Nur ein festgestelltes Ergebnis kann korrigiert werden")
            existing = next((x for x in result["corrections"] if x["status"] == "open"), None)
            if existing and existing["reason"] == reason:
                return self._project_and_materialize(work, result, actor)
            if existing:
                raise ExamResultConflictError("Für das Ergebnis ist bereits eine Korrektur offen")
            if any(day["status"] == "completed" for day in result["days"]) and reopening is None:
                raise ValueError(
                    "Nach Tagesabschluss ist eine zulässige Wiederöffnung nach #36 erforderlich"
                )
            work.repository.open_correction(
                {
                    "result_id": result_id,
                    "expected_result_version": expected,
                    "determination_id": current["id"],
                    "reason": reason,
                    "requested_by_member_id": member_id,
                    "reopening_reference": reopening,
                    "requested_at": _now(),
                }
            )
            work.repository.complete_result_day_mutation(
                result_id, "result_correction", payload, member_id, reason
            )
            updated = work.queries.result_by_id(result_id)
            assert updated is not None
            return self._project_and_materialize(work, updated, actor)

    def communicate(self, actor, result_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        expected = self._required_result_version(payload)
        method = self._required_text(payload.get("method"), "method", 300)
        communicated_at = self._required_datetime(payload.get("communicated_at"), "communicated_at")
        with self._unit_of_work_factory(write=True) as work:
            result = self._required_access(work, actor, result_id)
            member_id = actor["member_by_committee"].get(result["committee_id"])
            if member_id is None or not self._can_manage_committee(actor, result["committee_id"]):
                raise PermissionError("Forbidden.")
            determination = next(
                (x for x in result["determinations"] if x["status"] == "current"), None
            )
            if determination is None or result["correction_open"]:
                raise ValueError("Nur der aktuelle festgestellte Stand kann mitgeteilt werden")
            participants = set(determination["participant_member_ids"])
            confirmations = {
                x["committee_member_id"]
                for x in result["record_confirmations"]
                if x["determination_id"] == determination["id"]
            }
            if confirmations != participants:
                raise ValueError("Die Ergebnisniederschrift ist noch nicht vollständig bestätigt")
            existing = next(
                (
                    x
                    for x in result["communications"]
                    if x["determination_id"] == determination["id"] and x["status"] == "current"
                ),
                None,
            )
            if (
                existing
                and existing["method"] == method
                and existing["communicated_at"] == communicated_at
            ):
                return self._project_and_materialize(work, result, actor)
            work.repository.communicate_result(
                {
                    "result_id": result_id,
                    "expected_result_version": expected,
                    "determination_id": determination["id"],
                    "method": method,
                    "responsible_member_id": member_id,
                    "communicated_at": communicated_at,
                    "external_document_status": self._optional_text(
                        payload.get("external_document_status"), 300
                    ),
                    "external_document_reference": self._optional_text(
                        payload.get("external_document_reference"), 1000
                    ),
                    "created_at": _now(),
                }
            )
            work.repository.complete_result_day_mutation(
                result_id, "result_communicate", payload, member_id
            )
            updated = work.queries.result_by_id(result_id)
            assert updated is not None
            return self._project_and_materialize(work, updated, actor)

    def set_retention(self, actor, result_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        retention = self._retention_payload(payload)
        expected = self._required_result_version(payload)
        with self._unit_of_work_factory(write=True) as work:
            result = self._required_access(work, actor, result_id)
            member_id = actor["member_by_committee"].get(result["committee_id"])
            if member_id is None or not self._can_manage_committee(actor, result["committee_id"]):
                raise PermissionError("Forbidden.")
            model = result["model"]
            old = result["retention"]
            if self._same_retention(old, model, retention):
                return self._project_and_materialize(work, result, actor)
            if result["version"] != expected:
                raise ExamResultConflictError("Der Ergebnisstand wurde zwischenzeitlich geändert")
            hold_reason = self._retention_hold_reason(old, model, retention)
            work.repository.save_retention(
                {
                    "result_id": result_id,
                    "expected_result_version": expected,
                    "rule_reference": model["retention_rule_reference"],
                    "version": (old["version"] + 1 if old else 1),
                    "period_start": (
                        retention["period_start"].isoformat() if retention["period_start"] else None
                    ),
                    "retain_until": (
                        retention["retain_until"].isoformat() if retention["retain_until"] else None
                    ),
                    "legal_hold": retention["legal_hold"],
                    "hold_reason": hold_reason,
                    "release_reason": None,
                    "updated_by_member_id": member_id,
                    "updated_at": _now(),
                }
            )
            work.repository.complete_result_day_mutation(
                result_id, "result_retention", payload, member_id
            )
            updated = work.queries.result_by_id(result_id)
            assert updated is not None
            return self._project_and_materialize(work, updated, actor)

    def _retention_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if set(payload) - RETENTION_FIELDS:
            raise ValueError("Die Aufbewahrungsregel enthält unzulässige Felder")
        legal_hold = payload.get("legal_hold", False)
        if not isinstance(legal_hold, bool):
            raise ValueError("legal_hold muss ein boolescher Wert sein")
        hold_reason = self._optional_text(payload.get("hold_reason"), 3000)
        if legal_hold and hold_reason is None:
            raise ValueError("Eine Aufbewahrungssperre benötigt eine Begründung")
        period_start = self._optional_date(payload.get("period_start"), "period_start")
        retain_until = self._optional_date(payload.get("retain_until"), "retain_until")
        if retain_until is not None and period_start is None:
            raise ValueError("Eine Aufbewahrungsfrist benötigt einen Fristbeginn")
        return {
            "period_start": period_start,
            "retain_until": retain_until,
            "legal_hold": legal_hold,
            "hold_reason": hold_reason,
            "release_reason": payload.get("release_reason"),
        }

    @staticmethod
    def _same_retention(old, model, retention: dict[str, Any]) -> bool:
        if old is None:
            return False
        period_start = retention["period_start"]
        retain_until = retention["retain_until"]
        return (
            old["rule_reference"] == model["retention_rule_reference"]
            and old["period_start"] == (period_start.isoformat() if period_start else None)
            and old["retain_until"] == (retain_until.isoformat() if retain_until else None)
            and old["legal_hold"] == retention["legal_hold"]
            and old["hold_reason"] == retention["hold_reason"]
        )

    def _retention_hold_reason(self, old, model, retention: dict[str, Any]) -> str | None:
        period_start = retention["period_start"]
        retain_until = retention["retain_until"]
        if period_start and (
            retain_until is None
            or retain_until < self._add_years(period_start, model["retention_years"])
        ):
            raise ValueError("Die regelgebundene Mindestaufbewahrung darf nicht verkürzt werden")
        if (
            old
            and old["retain_until"]
            and (retain_until is None or retain_until.isoformat() < old["retain_until"])
        ):
            raise ValueError("Eine verbindliche Aufbewahrungsfrist darf nicht verkürzt werden")
        if old and old["legal_hold"] and not retention["legal_hold"]:
            release = self._optional_text(retention.get("release_reason"), 3000)
            if release is None:
                raise ValueError("Das Aufheben einer Sperre benötigt eine Begründung")
            return f"Freigabe: {release}"
        return retention["hold_reason"]

    @staticmethod
    def _add_years(value: date, years: int) -> date:
        try:
            return value.replace(year=value.year + years)
        except ValueError:
            return value.replace(month=2, day=28, year=value.year + years)

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

    def machine_export(self, actor, result_id: int) -> AssessmentMachineExportData:
        with self._unit_of_work_factory(write=True) as work:
            result = self._required_access(work, actor, result_id)
            member_id = actor["member_by_committee"].get(result["committee_id"])
            if member_id is None:
                raise PermissionError("Forbidden.")
            determination = next(
                (x for x in result["determinations"] if x["status"] == "current"), None
            )
            status = "determined" if determination else "draft"
            work.repository.record_export(
                {
                    "result_id": result_id,
                    "expected_result_version": result["version"],
                    "determination_id": determination["id"] if determination else None,
                    "export_kind": "machine",
                    "status": status,
                    "generated_by_member_id": member_id,
                    "generated_at": _now(),
                }
            )
            updated = work.queries.result_by_id(result_id)
            assert updated is not None
            view = self._project_and_materialize(work, updated, actor)
            return {
                "export_status": status,
                "official_document": False,
                "model_version": view["model_version"],
                "candidate": view["candidate"],
                "result": view,
            }

    def human_export(self, actor, result_id: int) -> AssessmentHumanExportData:
        with self._unit_of_work_factory(write=True) as work:
            result = self._required_access(work, actor, result_id)
            member_id = actor["member_by_committee"].get(result["committee_id"])
            if member_id is None:
                raise PermissionError("Forbidden.")
            determination = next(
                (x for x in result["determinations"] if x["status"] == "current"), None
            )
            status = "determined" if determination else "draft"
            work.repository.record_export(
                {
                    "result_id": result_id,
                    "expected_result_version": result["version"],
                    "determination_id": determination["id"] if determination else None,
                    "export_kind": "human",
                    "status": status,
                    "generated_by_member_id": member_id,
                    "generated_at": _now(),
                }
            )
            updated = work.queries.result_by_id(result_id)
            assert updated is not None
            view = self._project_and_materialize(work, updated, actor)
            human_result = {
                "id": view["id"],
                "state": view["state"],
                "model_version": view["model_version"],
                "candidate": view["candidate"],
                "external_results": view["external_results"],
                "committee_assessments": view["committee_assessments"],
                "current_calculation": view["current_calculation"],
                "current_determination": view["current_determination"],
                "correction_open": view["correction_open"],
                "communications": view["communications"],
            }
            return {"export_status": status, "official_document": False, "result": human_result}

    def completion_for_day(self, actor, day_id: int) -> dict[str, Any] | None:
        with self._unit_of_work_factory() as work:
            day = work.queries.day_completion(day_id)
            if day is None:
                return None
            if not self._can_read_committee(actor, day["committee_id"]):
                raise PermissionError("Forbidden.")
            rows = []
            for slot in day["slots"]:
                result = slot["result"]
                if result is None:
                    rows.append(
                        {
                            "exam_slot_id": slot["slot_id"],
                            "exam_result_id": None,
                            "state": "not_bound",
                            "day_assessments": [],
                            "day_assessments_complete": False,
                            "external_inputs_pending": [],
                            "overall_determination_pending": False,
                            "record_confirmations_complete": False,
                            "regular_close_ready": slot["execution_status"] == "cancelled",
                        }
                    )
                    continue
                if result["legacy_status"]:
                    rows.append(
                        {
                            "exam_slot_id": slot["slot_id"],
                            "exam_result_id": result["id"],
                            "state": result["legacy_status"],
                            "day_assessments": [],
                            "day_assessments_complete": True,
                            "external_inputs_pending": [],
                            "overall_determination_pending": False,
                            "record_confirmations_complete": True,
                            "regular_close_ready": True,
                        }
                    )
                    continue
                rules = result["model"]["rules"]
                day_assessments = [
                    {
                        "component_key": component["key"],
                        "label": component["label"],
                        "complete": self._component_score(result, component, strict=False)
                        is not None,
                    }
                    for component in rules["components"]
                    if component.get("day_scoped", False)
                ]
                external_pending = [
                    area["key"]
                    for area in rules["external_areas"]
                    if area["required"]
                    and not any(
                        item["area_key"] == area["key"] and item["status"] == "confirmed"
                        for item in result["external_results"]
                    )
                ]
                determination = next(
                    (x for x in result["determinations"] if x["status"] == "current"), None
                )
                confirmed = determination is None or {
                    item["committee_member_id"]
                    for item in result["record_confirmations"]
                    if item["determination_id"] == determination["id"]
                } == set(determination["participant_member_ids"])
                day_complete = all(item["complete"] for item in day_assessments)
                pending = result["state"] == "calculation_ready"
                rows.append(
                    {
                        "exam_slot_id": slot["slot_id"],
                        "exam_result_id": result["id"],
                        "state": result["state"],
                        "correction_open": result["correction_open"],
                        "day_assessments": day_assessments,
                        "day_assessments_complete": day_complete,
                        "external_inputs_pending": external_pending,
                        "overall_determination_pending": pending,
                        "record_confirmations_complete": confirmed,
                        "regular_close_ready": day_complete
                        and not pending
                        and confirmed
                        and not result["correction_open"],
                    }
                )
            return {
                "exam_day_id": day["day_id"],
                "slots": rows,
                "closing_ready": all(item["regular_close_ready"] for item in rows),
            }

    @staticmethod
    def _outcome(
        rules: dict[str, Any], weighted_total: Decimal, scores: dict[str, Decimal]
    ) -> dict[str, Any]:
        rounded = ExamResultService._round(weighted_total, rules["rounding"]["overall"])
        threshold = rounded if rules["rounding"]["threshold_basis"] == "rounded" else weighted_total
        grade = next(
            item["label"]
            for item in rules["grades"]
            if threshold >= Decimal(str(item["min_points"]))
        )
        passing = rules["passing"]
        passed = threshold >= Decimal(str(passing["overall_min"]))
        passed = passed and all(
            scores.get(key, Decimal(-1)) >= Decimal(str(minimum))
            for key, minimum in passing["component_minima"].items()
        )
        passed = passed and all(
            scores.get(key, Decimal(-1)) >= Decimal(str(minimum))
            for key, minimum in passing["external_minima"].items()
        )
        return {
            "rounded_total": rounded,
            "threshold_value": threshold,
            "grade": grade,
            "passed": passed,
        }

    @staticmethod
    def _assert_projection_access(
        result: AssessmentResultSnapshot, actor: AssessmentActorSnapshot
    ) -> None:
        actor_id = actor["member_by_committee"].get(result["committee_id"])
        can_manage = result["committee_id"] in actor["management_committee_ids"]
        if actor_id not in result["participant_member_ids"] and not can_manage:
            raise PermissionError("Forbidden.")

    def _project_and_materialize(
        self, work, result: AssessmentResultSnapshot, actor: AssessmentActorSnapshot
    ) -> dict[str, Any]:
        self._assert_projection_access(result, actor)
        actor_id = actor["member_by_committee"].get(result["committee_id"])
        participants = set(result["participant_member_ids"])
        can_manage = result["committee_id"] in actor["management_committee_ids"]
        rules = result["model"]["rules"]
        disclosed = {item["component_key"] for item in result["disclosures"]}
        visible = [
            item
            for item in result["individual_assessments"]
            if item["assessor_member_id"] == actor_id
            or (item["component_key"] in disclosed and actor_id in participants)
        ]
        calculations_disclosed = all(
            component["key"] in disclosed for component in rules["components"]
        )
        current_determination = next(
            (item for item in result["determinations"] if item["status"] == "current"), None
        )
        required_external_complete = all(
            not area["required"]
            or any(
                item["area_key"] == area["key"] and item["status"] == "confirmed"
                for item in result["external_results"]
            )
            for area in rules["external_areas"]
        )
        current_calculation = (
            result["calculations"][-1]
            if result["calculations"] and required_external_complete
            else None
        )
        view_state = result["state"]
        if not required_external_complete and current_determination is None:
            view_state = "incomplete"
        content_mutable = all(
            day["closure_status"] == "open"
            or (
                day["closure_status"] == "reopening"
                and result["id"] in day["reopening_assessment_result_ids"]
            )
            for day in result["days"]
        )
        counts: dict[str, dict[str, int]] = {}
        current_by_assessment: dict[tuple[str, str, int], dict[str, Any]] = {}
        for item in result["individual_assessments"]:
            if item["status"] != "superseded":
                current_by_assessment[
                    (item["component_key"], item["criterion_key"], item["assessor_member_id"])
                ] = item
        for item in current_by_assessment.values():
            values = counts.setdefault(item["component_key"], {"draft": 0, "submitted": 0})
            if item["status"] in values:
                values[item["status"]] += 1
        view = {
            "id": result["id"],
            "round_candidate_id": result["round_candidate_id"],
            "day_revisions": {str(day["day_id"]): day["revision"] for day in result["days"]},
            "version": result["version"],
            "state": view_state,
            "correction_open": result["correction_open"],
            "legacy_status": result["legacy_status"],
            "candidate": self._subject_view(result["subject"]),
            "binding": self._binding_view(result["binding"], result["model"]),
            "model_version": self._model_view(result["model"]),
            "participants": sorted(participants),
            "disclosures": list(result["disclosures"]),
            "individual_assessments": list(visible),
            "individual_assessment_counts": [
                {"component_key": key, **values} for key, values in sorted(counts.items())
            ],
            "committee_assessments": list(result["component_assessments"]),
            "external_results": list(result["external_results"]),
            "calculations": list(result["calculations"]) if calculations_disclosed else [],
            "current_calculation": (
                current_calculation
                if calculations_disclosed and required_external_complete
                else None
            ),
            "determinations": [
                {
                    **item,
                    "result_calculation_id": item["calculation_id"],
                    "confirmation_member_ids": sorted(
                        {
                            c["committee_member_id"]
                            for c in result["record_confirmations"]
                            if c["determination_id"] == item["id"]
                        }
                    ),
                }
                for item in result["determinations"]
            ],
            "current_determination": (
                {
                    **current_determination,
                    "result_calculation_id": current_determination["calculation_id"],
                    "confirmation_member_ids": sorted(
                        {
                            c["committee_member_id"]
                            for c in result["record_confirmations"]
                            if c["determination_id"] == current_determination["id"]
                        }
                    ),
                }
                if current_determination
                else None
            ),
            "corrections": [
                {**item, "result_determination_id": item["determination_id"]}
                for item in result["corrections"]
            ],
            "communications": [
                {**item, "result_determination_id": item["determination_id"]}
                for item in result["communications"]
            ],
            "retention": result["retention"],
            "exports": [
                {**item, "result_determination_id": item["determination_id"]}
                for item in result["exports"]
            ],
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
            "created_at": result["created_at"],
            "updated_at": result["updated_at"],
            "_links": {
                "self": {"href": f"/api/exam-results/{result['id']}"},
                "machine_export": {"href": f"/api/exam-results/{result['id']}/export.json"},
                "human_export": {"href": f"/api/exam-results/{result['id']}/export.txt"},
            },
        }
        return view

    @staticmethod
    def _model_view(model: AssessmentModelSnapshot) -> dict[str, Any]:
        return {
            "id": model["id"],
            "model_key": model["model_key"],
            "version": model["version"],
            "ihk": model["ihk"],
            "occupation": model["occupation"],
            "specialization": model["specialization"],
            "training_regulation": model["training_regulation"],
            "exam_regulation": model["exam_regulation"],
            "ihk_guidelines": model["ihk_guidelines"],
            "valid_from": model["valid_from"],
            "valid_until": model["valid_until"],
            "official_scale": {
                "min": model["official_scale_min"],
                "max": model["official_scale_max"],
            },
            "rules": model["rules"],
            "retention_rule_reference": model["retention_rule_reference"],
            "retention_years": model["retention_years"],
            "created_by_member_id": model["created_by_member_id"],
            "created_at": model["created_at"],
        }

    @staticmethod
    def _subject_view(subject: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": subject["candidate_id"],
            "first_name": subject["first_name"],
            "last_name": subject["last_name"],
            "ihk_exam_number": subject["ihk_exam_number"],
            "specialization": subject["specialization"],
        }

    @staticmethod
    def _binding_view(binding, model: AssessmentModelSnapshot) -> dict[str, Any]:
        return {
            "id": binding["id"],
            "exam_round_id": binding["round_id"],
            "assessment_model_version_id": binding["model_version_id"],
            "version": binding["version"],
            "bound_by_member_id": binding["bound_by_member_id"],
            "binding_reason": binding["binding_reason"],
            "bound_at": binding["bound_at"],
            "model": {
                key: model[key]
                for key in (
                    "model_key",
                    "version",
                    "ihk",
                    "occupation",
                    "specialization",
                    "valid_from",
                    "valid_until",
                )
            },
        }

    @staticmethod
    def _can_read_committee(actor: AssessmentActorSnapshot, committee_id: int) -> bool:
        return committee_id in actor["committee_ids"]

    @staticmethod
    def _can_manage_committee(actor: AssessmentActorSnapshot, committee_id: int) -> bool:
        return committee_id in actor["management_committee_ids"]

    def _assert_model_applicable(self, planning, identity, model: AssessmentModelSnapshot) -> None:
        if identity is None or identity["occupation"] != model["occupation"]:
            raise ValueError("Die Modellversion passt nicht zum Ausbildungsberuf des Ausschusses")
        if identity["ihk"] != model["ihk"]:
            raise ValueError("Die Modellversion passt nicht zur zuständigen IHK des Ausschusses")
        effective = date.fromisoformat(planning["effective_date"])
        if effective < date.fromisoformat(model["valid_from"]) or (
            model["valid_until"] is not None
            and effective > date.fromisoformat(model["valid_until"])
        ):
            raise ValueError("Die Modellversion ist für die Prüfungsrunde nicht gültig")
        specializations = {
            candidate["specialization"]
            for candidate in planning["candidates"]
            if candidate["is_active"]
        }
        if model["specialization"] is not None and specializations != {model["specialization"]}:
            raise ValueError("Die Modellversion passt nicht zu allen Schwerpunkten der Runde")

    @staticmethod
    def _validate_rules(raw: Any) -> dict[str, Any]:
        try:
            return AssessmentRules.model_validate(raw).as_json_data()
        except ValidationError as error:
            detail = error.errors()[0]
            location = ".".join(str(part) for part in detail["loc"])
            message = detail["msg"]
            if location and detail["type"] == "missing":
                message = f"{location} ist erforderlich"
            elif location:
                message = f"{location}: {message}"
            raise ValueError(message) from error

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
            parsed = Decimal(str(value))
        except InvalidOperation as error:
            raise ValueError(f"{field} muss eine Zahl sein") from error
        if not parsed.is_finite():
            raise ValueError(f"{field} muss endlich sein")
        return parsed

    @staticmethod
    def _required_text(value: Any, field: str, maximum: int) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} ist erforderlich")
        value = value.strip()
        if len(value) > maximum:
            raise ValueError(f"{field} ist zu lang")
        return value

    @staticmethod
    def _optional_text(value: Any, maximum: int) -> str | None:
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            raise ValueError("Textwert erwartet")
        value = value.strip()
        if len(value) > maximum:
            raise ValueError("Textwert ist zu lang")
        return value or None

    @staticmethod
    def _required_date(value: Any, field: str) -> date:
        if not isinstance(value, str):
            raise ValueError(f"{field} muss ein Datum sein")
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise ValueError(f"{field} muss ein ISO-Datum sein") from error

    def _optional_date(self, value: Any, field: str) -> date | None:
        return None if value is None or value == "" else self._required_date(value, field)

    @staticmethod
    def _required_result_version(payload: dict[str, Any]) -> int:
        value = payload.get("version")
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError("Eine gültige Ergebnisversion ist erforderlich")
        return value

    @staticmethod
    def _component(rules: dict[str, Any], key: str) -> dict[str, Any]:
        item = next((x for x in rules["components"] if x["key"] == key), None)
        if item is None:
            raise ValueError("Unbekannte Bewertungskomponente")
        return item

    @staticmethod
    def _criterion(component: dict[str, Any], key: str) -> dict[str, Any]:
        item = next((x for x in component["criteria"] if x["key"] == key), None)
        if item is None:
            raise ValueError("Unbekanntes Bewertungskriterium")
        return item

    @staticmethod
    def _external_area(rules: dict[str, Any], key: str) -> dict[str, Any]:
        item = next((x for x in rules["external_areas"] if x["key"] == key), None)
        if item is None:
            raise ValueError("Unbekannter externer Prüfungsbereich")
        return item

    @staticmethod
    def _participant_set(raw: Any) -> set[int]:
        if not isinstance(raw, list) or any(
            not isinstance(x, int) or isinstance(x, bool) or x < 1 for x in raw
        ):
            raise ValueError("participant_member_ids muss eine Liste gültiger IDs sein")
        if len(set(raw)) != len(raw):
            raise ValueError("Mitwirkende dürfen nicht doppelt angegeben werden")
        return set(raw)

    def _validate_vote(self, raw: Any, members: set[int]) -> dict[str, list[int]]:
        if not isinstance(raw, dict) or set(raw) != {"yes", "no", "abstain"}:
            raise ValueError("Das Abstimmungsergebnis ist unvollständig")
        vote = {key: sorted(self._participant_set(raw[key])) for key in raw}
        voters = set(vote["yes"]) | set(vote["no"]) | set(vote["abstain"])
        if voters != members or sum(len(x) for x in vote.values()) != len(members):
            raise ValueError("Jedes mitwirkende Mitglied benötigt genau eine Stimme")
        if len(vote["yes"]) <= len(vote["no"]):
            raise ValueError("Der Beschluss hat keine Mehrheit")
        return vote

    def _validate_dissent(self, raw: Any, members: set[int]) -> list[dict[str, Any]]:
        if not isinstance(raw, list):
            raise ValueError("Abweichende Voten müssen als Liste übermittelt werden")
        dissent = []
        for item in raw:
            if not isinstance(item, dict) or set(item) != {"member_id", "statement"}:
                raise ValueError("Ein abweichendes Votum ist unvollständig")
            member_id = self._integer(item["member_id"], "member_id", 1)
            if member_id not in members:
                raise ValueError("Ein abweichendes Votum gehört nicht zum beschließenden Gremium")
            dissent.append(
                {
                    "member_id": member_id,
                    "statement": self._required_text(item["statement"], "statement", 3000),
                }
            )
        return dissent

    @staticmethod
    def _assert_quorum(rules: dict[str, Any], chosen: set[int], actual: set[int]) -> None:
        if not chosen or not chosen.issubset(actual):
            raise ValueError("Nur tatsächlich mitwirkende Prüfer dürfen beschließen")
        if len(chosen) < int(rules["quorum"]["minimum_members"]):
            raise ValueError("Das Gremium ist nicht ordnungsgemäß besetzt")

    @staticmethod
    def _round(value: Decimal, rule: dict[str, Any]) -> Decimal:
        if rule["mode"] == "none":
            return value
        return value.quantize(Decimal(1).scaleb(-int(rule["digits"])), rounding=ROUND_HALF_UP)

    def _calculation_command(self, result: AssessmentResultSnapshot) -> CalculationCommand | None:
        rules = result["model"]["rules"]
        inputs = []
        scores = {}
        weighted_total = Decimal(0)
        for component in rules["components"]:
            score = self._component_score(result, component, strict=True)
            if score is None:
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
            external = next(
                (
                    x
                    for x in reversed(result["external_results"])
                    if x["area_key"] == area["key"] and x["status"] in {"confirmed", "unconfirmed"}
                ),
                None,
            )
            if area["required"] and (external is None or external["status"] != "confirmed"):
                return None
            if external is None or external["status"] != "confirmed":
                continue
            score = Decimal(external["points"])
            weighted_total += score * Decimal(str(area["weight"])) / Decimal(100)
            scores[area["key"]] = score
            inputs.append(
                {
                    "kind": "external",
                    "key": area["key"],
                    "points": external["points"],
                    "weight": str(area["weight"]),
                    "revision_id": external["id"],
                }
            )
        rounded = self._round(weighted_total, rules["rounding"]["overall"])
        threshold = rounded if rules["rounding"]["threshold_basis"] == "rounded" else weighted_total
        grade = next(
            item["label"]
            for item in rules["grades"]
            if threshold >= Decimal(str(item["min_points"]))
        )
        passing = rules["passing"]
        passed = threshold >= Decimal(str(passing["overall_min"]))
        passed = passed and all(
            scores.get(key, Decimal(-1)) >= Decimal(str(minimum))
            for key, minimum in passing["component_minima"].items()
        )
        passed = passed and all(
            scores.get(key, Decimal(-1)) >= Decimal(str(minimum))
            for key, minimum in passing["external_minima"].items()
        )
        path = {
            "inputs": inputs,
            "unrounded_total": _decimal_text(weighted_total),
            "rounded_total": _decimal_text(rounded),
            "threshold_basis": rules["rounding"]["threshold_basis"],
        }
        payload = {
            "model": result["model"]["id"],
            "inputs": inputs,
            "unrounded_total": _decimal_text(weighted_total),
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if any(x["input_fingerprint"] == fingerprint for x in result["calculations"]):
            return None
        command: CalculationCommand = {
            "result_id": result["id"],
            "expected_result_version": result["version"],
            "result_state": (
                result["state"]
                if any(x["status"] == "current" for x in result["determinations"])
                else "calculation_ready"
            ),
            "version": max((x["version"] for x in result["calculations"]), default=0) + 1,
            "input_fingerprint": fingerprint,
            "total_points": _decimal_text(rounded),
            "grade": grade,
            "passed": passed,
            "path": path,
            "created_at": _now(),
        }
        return command

    def _ensure_calculation(self, work, result: AssessmentResultSnapshot):
        command = self._calculation_command(result)
        if command is None:
            return result
        work.repository.save_calculation(command)
        updated = work.queries.result_by_id(result["id"])
        return updated or result

    def _required_access(self, work, actor: AssessmentActorSnapshot, result_id: int):
        result = work.queries.result_by_id(result_id)
        if result is None:
            raise ValueError("Ergebnisvorgang nicht gefunden")
        if result["legacy_status"] is not None:
            raise ValueError("Für diesen Altvorgang liegen keine Ergebnisdaten in lzug vor")
        member_id = actor["member_by_committee"].get(result["committee_id"])
        if member_id not in result["participant_member_ids"] and not self._can_manage_committee(
            actor, result["committee_id"]
        ):
            raise PermissionError("Forbidden.")
        return result

    @staticmethod
    def _assert_inputs_mutable(result: AssessmentResultSnapshot) -> None:
        if result["state"] in {"determined", "communicated"} and not result["correction_open"]:
            raise ExamResultConflictError(
                "Ein festgestelltes Ergebnis benötigt einen begründeten Korrekturvorgang"
            )

    @staticmethod
    def _latest_individual(items, component_key: str, criterion_key: str, member_id: int):
        matches = [
            x
            for x in items
            if x["component_key"] == component_key
            and x["criterion_key"] == criterion_key
            and x["assessor_member_id"] == member_id
            and x["status"] != "superseded"
        ]
        return max(matches, key=lambda x: x["revision"], default=None)

    def _current_individuals(self, result: AssessmentResultSnapshot):
        latest = {}
        for item in result["individual_assessments"]:
            if item["status"] != "superseded":
                latest[
                    (item["component_key"], item["criterion_key"], item["assessor_member_id"])
                ] = item
        return list(latest.values())

    def _individual_component_complete(self, result, component, participants: set[int]) -> bool:
        criteria = {x["key"] for x in component["criteria"]}
        by_member: dict[int, set[str]] = {}
        for item in self._current_individuals(result):
            if item["component_key"] == component["key"] and item["status"] == "submitted":
                by_member.setdefault(item["assessor_member_id"], set()).add(item["criterion_key"])
        complete = {
            member_id
            for member_id, submitted in by_member.items()
            if member_id in participants and submitted == criteria
        }
        return len(complete) >= int(component["required_assessors"])

    def _component_score(self, result, component, *, strict: bool) -> Decimal | None:
        if component["mode"] == "committee":
            assessment = next(
                (
                    x
                    for x in result["component_assessments"]
                    if x["component_key"] == component["key"] and x["status"] == "current"
                ),
                None,
            )
            return Decimal(assessment["points"]) if assessment else None
        participant_ids = set(result["participant_member_ids"])
        current = [
            x
            for x in self._current_individuals(result)
            if x["component_key"] == component["key"]
            and x["status"] == "submitted"
            and x["assessor_member_id"] in participant_ids
        ]
        by_assessor: dict[int, dict[str, Any]] = {}
        for item in current:
            by_assessor.setdefault(item["assessor_member_id"], {})[item["criterion_key"]] = item
        criterion_keys = {x["key"] for x in component["criteria"]}
        scores = []
        for assessments in by_assessor.values():
            if set(assessments) != criterion_keys:
                continue
            score = sum(
                Decimal(assessments[c["key"]]["normalized_points"])
                * Decimal(str(c["weight"]))
                / Decimal(100)
                for c in component["criteria"]
            )
            scores.append(self._round(score, result["model"]["rules"]["rounding"]["intermediate"]))
        required = int(component["required_assessors"])
        if len(scores) < required:
            return None
        if (
            component["additional_assessor_on_deviation"]
            and max(scores) - min(scores) > Decimal(str(component["max_deviation"]))
            and len(scores) < required + 1
        ):
            return None
        return sum(scores, Decimal(0)) / Decimal(len(scores))
