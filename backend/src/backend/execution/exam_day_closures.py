"""Revision-bound formal closure and targeted reopening of complete exam days."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any, cast

from backend.execution.day_closure_policy import (
    day_closure_view,
    evaluate_day_closure,
)
from backend.execution.day_closure_snapshot import ExamDayClosureReadSnapshot
from backend.execution.day_lifecycle_contracts import (
    ExamDayClosureIntent,
    ExamDayClosureOutcome,
    ExamDayConflictError,
    ExamDayLifecycleSnapshot,
    ExamDayReopeningIntent,
    ExamDayValidationError,
    NotificationJob,
)
from backend.execution.lifecycle_ports import (
    DayCloseCommand,
    DayClosureFacts,
    DayReopenCommand,
    PlanAssignmentLifecycleSnapshot,
    PlanSlotLifecycleSnapshot,
)
from backend.execution.protocol_ports import ExecutionProtocolSnapshot
from backend.identity.authorization import AuthorizationScope
from backend.notifications.service import NotificationService
from backend.presentation.exam_exports import render_day_closure_export

CLOSED_STATUSES = {"closed", "closed_exception", "historical"}
REOPENING_SCOPE_KINDS = {
    "slot_status",
    "candidate_attendance",
    "member_attendance",
    "staffing",
    "absence",
    "exam_protocol",
    "exam_result",
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _token(kind: str, entity_id: int) -> str:
    return f"{kind}:{entity_id}"


class ExamDayClosureService:
    """Validate day transitions, calculate impacts, notify, and export read snapshots."""

    def __init__(
        self,
        *,
        notification_service: NotificationService,
    ) -> None:
        self.notification_service = notification_service

    def export_from_read_snapshot(
        self,
        scope: AuthorizationScope,
        facts: DayClosureFacts,
        read_snapshot: ExamDayClosureReadSnapshot | None,
        *,
        human: bool,
    ) -> dict[str, Any] | str:
        if read_snapshot is None:
            raise ValueError("Prüfungstag nicht gefunden")
        closure = day_closure_view(scope, facts, read_snapshot)
        if closure is None:
            raise ValueError("Prüfungstag nicht gefunden")
        day = read_snapshot.day
        export = {
            "export_version": 1,
            "exam_day": {
                "id": day["id"],
                "date": day["date"],
                "exam_round_id": day["exam_round_id"],
            },
            "closure": closure,
        }
        if human:
            return self._render_human_export(export)
        return export

    def evaluate_close_intent(
        self,
        scope: AuthorizationScope,
        day_id: int,
        command: DayCloseCommand,
        facts: DayClosureFacts,
        snapshot: ExamDayLifecycleSnapshot | None,
    ) -> ExamDayClosureIntent:
        """Validate one close against detached owner facts without applying writes."""
        if snapshot is None:
            raise ValueError("Prüfungstag nicht gefunden")
        expected_revision, closure_type, reason, attempts, fingerprint = self._close_command(
            command.payload()
        )
        day = snapshot.day
        if day["id"] != day_id:
            raise ValueError("Prüfungstag nicht gefunden")
        if not scope.can_manage_committee(facts.committee_id):
            raise PermissionError("Forbidden.")
        actor_id = scope.member_for_committee(facts.committee_id)
        if actor_id is None:
            raise PermissionError("Forbidden.")
        if fingerprint in snapshot.closure_fingerprints:
            return ExamDayClosureIntent(
                int(day["id"]),
                expected_revision,
                closure_type,
                reason,
                attempts,
                fingerprint,
                actor_id,
                facts.committee_id,
                cast(int, day["exam_round_id"]),
                None,
                {},
                replayed=True,
            )
        reopening = self._prepare_closure_snapshot(snapshot, expected_revision)
        evaluation = evaluate_day_closure(facts, day_id)
        ready_key = "regular_close_ready" if closure_type == "regular" else "exception_close_ready"
        if not evaluation[ready_key]:
            raise ExamDayValidationError(
                "Die Voraussetzungen für diesen Tagesabschluss sind nicht erfüllt",
                [item for item in evaluation["items"] if not item["ok"]],
            )
        return ExamDayClosureIntent(
            int(day["id"]),
            expected_revision,
            closure_type,
            reason,
            attempts,
            fingerprint,
            actor_id,
            facts.committee_id,
            cast(int, day["exam_round_id"]),
            cast(int, reopening["id"]) if reopening is not None else None,
            evaluation,
        )

    def evaluate_reopen_intent(
        self,
        scope: AuthorizationScope,
        day_id: int,
        command: DayReopenCommand,
        facts: DayClosureFacts,
        snapshot: ExamDayLifecycleSnapshot | None,
    ) -> ExamDayReopeningIntent:
        """Validate reopening and materialize its impact without applying mutations."""
        if snapshot is None:
            raise ValueError("Prüfungstag nicht gefunden")
        payload = command.payload()
        expected_revision = self._required_revision(payload)
        occasion = self._required_text(payload.get("occasion"), "occasion", 1000)
        source = self._required_text(payload.get("source"), "source", 1000)
        reason = self._required_text(payload.get("reason"), "reason", 3000)
        requested_scope = self._normalize_scope(payload.get("scope"))
        fingerprint = _fingerprint(
            {
                "revision": expected_revision,
                "occasion": occasion,
                "source": source,
                "reason": reason,
                "scope": requested_scope,
            }
        )
        day = snapshot.day
        if day["id"] != day_id:
            raise ValueError("Prüfungstag nicht gefunden")
        if not scope.can_manage_committee(facts.committee_id):
            raise PermissionError("Forbidden.")
        actor_id = scope.member_for_committee(facts.committee_id)
        if actor_id is None:
            raise PermissionError("Forbidden.")
        if any(item["command_fingerprint"] == fingerprint for item in snapshot.reopenings):
            return ExamDayReopeningIntent(
                int(day["id"]),
                expected_revision,
                occasion,
                source,
                reason,
                fingerprint,
                actor_id,
                facts.committee_id,
                cast(int, day["exam_round_id"]),
                {},
                replayed=True,
            )
        if day["revision"] != expected_revision:
            raise ExamDayConflictError("Der Prüfungstag wurde zwischenzeitlich geändert")
        if day["closure_status"] not in CLOSED_STATUSES:
            raise ExamDayConflictError(
                "Nur ein geschlossener Prüfungstag kann wieder geöffnet werden"
            )
        if any(item["status"] == "open" for item in snapshot.reopenings):
            raise ExamDayConflictError("Für den Prüfungstag läuft bereits eine Wiederöffnung")
        impact = self._impact(day, payload.get("scope"), facts=facts)
        return ExamDayReopeningIntent(
            int(day["id"]),
            expected_revision,
            occasion,
            source,
            reason,
            fingerprint,
            actor_id,
            facts.committee_id,
            cast(int, day["exam_round_id"]),
            impact,
        )

    def publish_close_notifications(self, outcome: ExamDayClosureOutcome) -> None:
        """Publish close notifications only after the caller has committed."""
        if outcome.committee_id is None or outcome.round_id is None or outcome.day_id is None:
            return
        self._notify(
            outcome.committee_id,
            outcome.round_id,
            outcome.day_id,
            list(outcome.notification_jobs),
        )

    def _close_command(
        self, payload: dict[str, Any]
    ) -> tuple[int, str, str | None, str | None, str]:
        expected_revision = self._required_revision(payload)
        closure_type = payload.get("closure_type", "regular")
        if closure_type not in {"regular", "exception"}:
            raise ValueError("Unbekannte Abschlussart")
        if payload.get("confirmed") is not True:
            raise ValueError("Die angezeigten Abschlussvoraussetzungen müssen bestätigt werden")
        reason = self._optional_text(payload.get("reason"), 3000)
        attempts = self._optional_text(payload.get("clarification_attempts"), 3000)
        if closure_type == "regular":
            reason, attempts = None, None
        if closure_type == "exception" and (reason is None or attempts is None):
            raise ValueError(
                "Ein Ausnahmeabschluss benötigt Grund und dokumentierte Klärungsversuche"
            )
        command = {
            "revision": expected_revision,
            "closure_type": closure_type,
            "confirmed": True,
            "reason": reason,
            "clarification_attempts": attempts,
        }
        return expected_revision, closure_type, reason, attempts, _fingerprint(command)

    @staticmethod
    def _prepare_closure_snapshot(
        snapshot: ExamDayLifecycleSnapshot, expected_revision: int
    ) -> Mapping[str, object] | None:
        day = snapshot.day
        if day["revision"] != expected_revision:
            raise ExamDayConflictError("Der Prüfungstag wurde zwischenzeitlich geändert")
        if day["closure_status"] not in {"open", "reopening"}:
            raise ExamDayConflictError("Der Prüfungstag ist bereits formal geschlossen")
        reopening = next((item for item in snapshot.reopenings if item["status"] == "open"), None)
        if day["closure_status"] == "reopening":
            if reopening is None:
                raise ExamDayConflictError("Der Wiederöffnungsstand ist inkonsistent")
            requested = set(cast(Sequence[str], reopening["requested_scope"]))
            completed = set(cast(Sequence[str], reopening["completed_scope"]))
            if not requested.issubset(completed):
                raise ExamDayValidationError(
                    "Der wieder geöffnete Korrekturumfang ist noch nicht vollständig bearbeitet",
                    [
                        {
                            "code": "reopening_scope_unresolved",
                            "label": "Korrekturumfang bearbeiten",
                            "ok": False,
                            "details": sorted(requested - completed),
                        }
                    ],
                )
        return reopening

    def reopening_impact_from_facts(
        self,
        scope: AuthorizationScope,
        day_id: int,
        raw_scope: Any,
        facts: DayClosureFacts,
        snapshot: ExamDayLifecycleSnapshot | None,
    ) -> dict[str, Any]:
        if snapshot is None or snapshot.day["id"] != day_id:
            raise ValueError("Prüfungstag nicht gefunden")
        day = snapshot.day
        if not scope.can_manage_committee(facts.committee_id):
            raise PermissionError("Forbidden.")
        if day["closure_status"] not in CLOSED_STATUSES:
            raise ExamDayConflictError(
                "Nur ein geschlossener Prüfungstag kann wieder geöffnet werden"
            )
        if any(item["status"] == "open" for item in snapshot.reopenings):
            raise ExamDayConflictError("Für den Prüfungstag läuft bereits eine Wiederöffnung")
        return self._impact(day, raw_scope, facts=facts)

    def publish_reopening_notifications(self, outcome: ExamDayClosureOutcome) -> None:
        """Publish reopening notifications only after the caller has committed."""
        if outcome.committee_id is None or outcome.round_id is None or outcome.day_id is None:
            return
        self._notify(
            outcome.committee_id,
            outcome.round_id,
            outcome.day_id,
            list(outcome.notification_jobs),
        )

    @staticmethod
    def _render_human_export(export: dict[str, Any]) -> str:
        day = export["exam_day"]
        closure = export["closure"]
        return render_day_closure_export(day, closure)

    def _impact(
        self,
        day: Mapping[str, object],
        raw_scope: Any,
        *,
        facts: DayClosureFacts,
    ) -> dict[str, Any]:
        requested = self._normalize_scope(raw_scope)
        slots = {item.id: item for item in facts.slots}
        assignments = {item.id: item for item in facts.assignments}
        absences = {item["id"]: item for item in facts.absences}
        protocols = {
            protocol["id"]: protocol
            for item in (facts.protocol_day_snapshot or {}).get("slots", ())
            if (protocol := item["protocol"]) is not None
        }
        results = {item["id"]: item["round_candidate_id"] for item in facts.assessment_results}
        self._validate_reopening_scope(requested, slots, assignments, absences, protocols, results)
        protocol_ids, result_ids = self._impacted_entity_ids(requested, slots, protocols, results)
        details = self._snapshot_impact_details(
            protocols, protocol_ids, result_ids, facts.assessment_impacts
        )
        expanded = set(requested)
        expanded.update(_token("exam_protocol", item) for item in protocol_ids)
        expanded.update(_token("exam_result", item) for item in result_ids)
        return {
            "exam_day_id": cast(int, day["id"]),
            "revision": cast(int, day["revision"]),
            "requested_scope": requested,
            "expanded_scope": sorted(expanded),
            "impacts": details,
        }

    @staticmethod
    def _validate_reopening_scope(
        requested: list[str],
        slots: dict[int, PlanSlotLifecycleSnapshot],
        assignments: dict[int, PlanAssignmentLifecycleSnapshot],
        absences: dict[int, Any],
        protocols: dict[int, Any],
        results: dict[int, int],
    ) -> None:
        for token in requested:
            kind, raw_id = token.split(":", 1)
            entity_id = int(raw_id)
            valid = (
                (kind in {"slot_status", "candidate_attendance"} and entity_id in slots)
                or (kind in {"member_attendance", "staffing"} and entity_id in assignments)
                or (kind == "absence" and entity_id in absences)
                or (kind == "exam_protocol" and entity_id in protocols)
                or (kind == "exam_result" and entity_id in results)
            )
            if not valid:
                raise ValueError("Der Korrekturumfang gehört nicht zum ausgewählten Prüfungstag")

    @staticmethod
    def _impacted_entity_ids(
        requested: list[str],
        slots: dict[int, PlanSlotLifecycleSnapshot],
        protocols: dict[int, Any],
        results: dict[int, int],
    ) -> tuple[set[int], set[int]]:
        impacted_protocol_ids: set[int] = set()
        impacted_result_ids: set[int] = set()
        broad = any(
            token.split(":", 1)[0] in {"member_attendance", "staffing", "absence"}
            for token in requested
        )
        if broad:
            impacted_protocol_ids.update(protocols)
            impacted_result_ids.update(results)
        for token in requested:
            kind, raw_id = token.split(":", 1)
            entity_id = int(raw_id)
            if kind in {"slot_status", "candidate_attendance"}:
                slot = slots[entity_id]
                impacted_protocol_ids.update(
                    protocol_id
                    for protocol_id, protocol in protocols.items()
                    if ExamDayClosureService._protocol_slot_id(protocol) == slot.id
                )
                impacted_result_ids.update(
                    result_id
                    for result_id, candidate_id in results.items()
                    if candidate_id == slot.round_candidate_id
                )
            elif kind == "exam_protocol":
                impacted_protocol_ids.add(entity_id)
                slot = slots[ExamDayClosureService._protocol_slot_id(protocols[entity_id])]
                impacted_result_ids.update(
                    result_id
                    for result_id, candidate_id in results.items()
                    if candidate_id == slot.round_candidate_id
                )
            elif kind == "exam_result":
                impacted_result_ids.add(entity_id)
        return impacted_protocol_ids, impacted_result_ids

    @staticmethod
    def _protocol_slot_id(protocol: Any) -> int:
        if isinstance(protocol, Mapping):
            return int(protocol["exam_slot_id"])
        return protocol.exam_slot_id

    def _snapshot_impact_details(
        self,
        protocols: Mapping[int, ExecutionProtocolSnapshot],
        impacted_protocol_ids: set[int],
        impacted_result_ids: set[int],
        assessment_impacts: Sequence[Mapping[str, Any]],
    ) -> dict[str, list[int]]:
        recipient_ids: set[int] = set()
        invalidated_response_ids: list[int] = []
        for protocol_id in impacted_protocol_ids:
            protocol = protocols[protocol_id]
            revision = next(
                (
                    item
                    for item in protocol["revisions"]
                    if item["version"] == protocol["current_version"]
                ),
                None,
            )
            if revision is None:
                raise ValueError("Der aktuelle Protokollstand fehlt")
            responses = revision["responses"]
            invalidated_response_ids.extend(item["id"] for item in responses)
            recipient_ids.update(item["committee_member_id"] for item in responses)
            recipient_ids.update(protocol["participants"])
        result_impacts = self._result_impact_details(
            impacted_result_ids, recipient_ids, assessment_impacts
        )
        return {
            "exam_protocol_ids": sorted(impacted_protocol_ids),
            "invalidated_protocol_response_ids": sorted(invalidated_response_ids),
            "exam_result_ids": sorted(impacted_result_ids),
            **result_impacts,
            "recipient_member_ids": sorted(recipient_ids),
        }

    def _result_impact_details(
        self,
        impacted_result_ids: set[int],
        recipient_ids: set[int],
        assessment_impacts: Sequence[Mapping[str, Any]],
    ) -> dict[str, list[int]]:
        determination_ids: list[int] = []
        communicated_result_ids: list[int] = []
        ihk_processed_result_ids: list[int] = []
        for result in assessment_impacts:
            if result["id"] not in impacted_result_ids:
                continue
            determination = result["current_determination"]
            if determination is None:
                continue
            result_id = result["id"]
            determination_ids.append(determination["id"])
            recipient_ids.update(determination["participant_member_ids"])
            communications = result["communications"]
            if communications:
                communicated_result_ids.append(result_id)
            if any(item["external_document_status"] for item in communications):
                ihk_processed_result_ids.append(result_id)
        return {
            "affected_result_determination_ids": sorted(determination_ids),
            "communicated_result_ids": sorted(communicated_result_ids),
            "ihk_processed_result_ids": sorted(ihk_processed_result_ids),
        }

    def _notify(
        self,
        committee_id: int,
        round_id: int,
        day_id: int,
        jobs: list[NotificationJob],
    ) -> None:
        for job in jobs:
            try:
                self.notification_service.create_direct(
                    committee_id=committee_id,
                    round_id=round_id,
                    recipient_member_ids=job.recipient_member_ids,
                    event_type=job.event_type,
                    title=job.title,
                    message=job.message,
                    action_path=f"/confirmed-plan-days/{day_id}",
                    origin_key=job.origin_key,
                )
            except Exception:
                # The durable task and domain decision remain committed; delivery problems
                # are deliberately handled by the notification contract.
                continue

    @staticmethod
    def _required_revision(payload: dict[str, Any]) -> int:
        value = payload.get("revision")
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError("Eine aktuelle Tagesrevision ist erforderlich")
        return value

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
        if value is None:
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
    def _normalize_scope(raw_scope: Any) -> list[str]:
        if not isinstance(raw_scope, list) or not raw_scope:
            raise ValueError("Eine Wiederöffnung benötigt einen konkreten Korrekturumfang")
        tokens: set[str] = set()
        for item in raw_scope:
            if not isinstance(item, dict) or set(item) != {"kind", "entity_id"}:
                raise ValueError("Ungültiger Korrekturumfang")
            kind = item.get("kind")
            entity_id = item.get("entity_id")
            if kind not in REOPENING_SCOPE_KINDS:
                raise ValueError("Unbekannter Korrekturumfang")
            if not isinstance(entity_id, int) or isinstance(entity_id, bool) or entity_id < 1:
                raise ValueError("Ungültige Kennung im Korrekturumfang")
            tokens.add(_token(kind, entity_id))
        return sorted(tokens)
