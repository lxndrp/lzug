"""Versioned, jointly confirmed protocols for exams that actually started."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.execution.protocol_ports import (
    ExecutionProtocolSnapshot,
    ExecutionProtocolUnitOfWork,
    ExecutionProtocolUnitOfWorkFactory,
    ProtocolContentCommand,
    ProtocolCorrectionOpenCommand,
    ProtocolCorrectionRequestCommand,
    ProtocolEntryDraft,
    ProtocolReferencesSnapshot,
    ProtocolResponseCommand,
    ProtocolRetentionCommand,
    ProtocolRevisionSnapshot,
    ProtocolVersionCommand,
)
from backend.execution.slot_ports import DayMutationRequest
from backend.identity.authorization import AuthorizationScope

DECLARATIONS = {"without_special_occurrences", "with_special_occurrences"}
ENTRY_CATEGORIES = {
    "late_start",
    "interruption",
    "termination",
    "different_staffing",
    "procedural_deviation",
    "objection_or_reservation",
    "other",
}
RESPONSE_TYPES = {"confirmed", "reservation"}
COMPLETE_STATES = {"fully_confirmed", "fully_with_reservation"}
ENTRY_FIELDS = {"category", "statement", "occurred_from", "occurred_to"}


class ExamProtocolConflictError(ValueError):
    """Signal an optimistic-lock or non-idempotent repeated action conflict."""


class ExamProtocolService:
    """Apply protocol state, access, history, retention, and export contracts."""

    def __init__(self, unit_of_work_factory: ExecutionProtocolUnitOfWorkFactory, *, clock=None):
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock or (lambda: datetime.now(UTC).replace(microsecond=0).isoformat())

    def get_by_slot(self, scope: AuthorizationScope, slot_id: int) -> dict[str, Any] | None:
        with self._unit_of_work_factory() as work:
            protocol = work.protocol_by_slot(slot_id)
            if protocol is None:
                return None
            self._require_access(protocol, scope)
            return self._view(protocol, scope)

    def get(self, scope: AuthorizationScope, protocol_id: int) -> dict[str, Any] | None:
        with self._unit_of_work_factory() as work:
            protocol = work.protocol_by_id(protocol_id)
            if protocol is None:
                return None
            self._require_access(protocol, scope)
            return self._view(protocol, scope)

    def update_content(
        self, scope: AuthorizationScope, protocol_id: int, payload: ProtocolContentCommand
    ) -> dict[str, Any]:
        declaration, entries = self._normalize_content(payload)
        expected_version = self._required_version(payload)
        with self._unit_of_work_factory(write=True) as work:
            protocol = self._required_protocol(work, protocol_id)
            actor_id, participants, can_manage = self._require_access(protocol, scope, edit=True)
            current = self._current_revision(protocol)
            if current["version"] != expected_version:
                if (
                    current["previous_revision_id"] is not None
                    and current["version"] == expected_version + 1
                    and self._revision_content(current) == (declaration, entries)
                ):
                    return self._view(protocol, scope)
                raise ExamProtocolConflictError(
                    "Der Protokollstand wurde zwischenzeitlich geändert"
                )
            if self._state(protocol, current) in COMPLETE_STATES:
                raise ExamProtocolConflictError(
                    "Ein vollständig behandelter Stand benötigt einen Korrekturvorgang"
                )
            if actor_id is None or (
                actor_id not in participants
                and not (can_manage and current["workflow_state"] == "correction_open")
            ):
                raise PermissionError("Forbidden.")
            handle = self._guard_day_mutation(
                work,
                protocol,
                "exam_protocol",
                payload.get("expected_day_revision"),
                actor_id,
            )
            change_reason = self._optional_text(payload.get("change_reason"), 1000)
            work.write_protocol_revision(
                {
                    "protocol_id": protocol_id,
                    "expected_version": current["version"],
                    "declaration": declaration,
                    "workflow_state": (
                        "correction_open"
                        if current["workflow_state"] == "correction_open"
                        else "draft"
                    ),
                    "previous_revision_id": current["id"],
                    "correction_request_id": current["correction_request_id"],
                    "actor_member_id": actor_id,
                    "change_reason": change_reason,
                    "created_at": self._now(),
                    "entries": entries,
                }
            )
            work.complete_day_mutation(handle, actor_member_id=actor_id, reason=change_reason)
            return self._view(self._required_protocol(work, protocol_id), scope)

    def submit(
        self, scope: AuthorizationScope, protocol_id: int, payload: ProtocolVersionCommand
    ) -> dict[str, Any]:
        expected_version = self._required_version(payload)
        with self._unit_of_work_factory(write=True) as work:
            protocol = self._required_protocol(work, protocol_id)
            actor_id, participants, _managed = self._require_access(protocol, scope, react=True)
            revision = self._current_revision(protocol)
            self._assert_version(revision, expected_version)
            if revision["submitted_at"] is not None:
                return self._view(protocol, scope)
            if actor_id not in participants:
                raise PermissionError("Forbidden.")
            self._validate_persisted_content(revision)
            handle = self._guard_day_mutation(
                work,
                protocol,
                "exam_protocol",
                payload.get("expected_day_revision"),
                actor_id,
            )
            submitted_at = self._now()
            work.submit_protocol_revision(
                {
                    "protocol_id": protocol_id,
                    "version": revision["version"],
                    "actor_member_id": actor_id,
                    "submitted_at": submitted_at,
                }
            )
            work.complete_day_mutation(handle, actor_member_id=actor_id)
            return self._view(self._required_protocol(work, protocol_id), scope)

    def respond(
        self, scope: AuthorizationScope, protocol_id: int, payload: ProtocolResponseCommand
    ) -> dict[str, Any]:
        expected_version = self._required_version(payload)
        response_type = payload.get("response")
        if response_type not in RESPONSE_TYPES:
            raise ValueError("Unbekannte Protokollreaktion")
        with self._unit_of_work_factory(write=True) as work:
            protocol = self._required_protocol(work, protocol_id)
            actor_id, participants, _managed = self._require_access(protocol, scope, react=True)
            revision = self._current_revision(protocol)
            self._assert_version(revision, expected_version)
            if revision["submitted_at"] is None:
                raise ValueError("Das Protokoll wurde noch nicht zur Bestätigung vorgelegt")
            if actor_id not in participants:
                raise PermissionError("Forbidden.")
            entry_id, statement = self._response_details(revision, response_type, payload)
            existing = next(
                (
                    response
                    for response in revision["responses"]
                    if response["committee_member_id"] == actor_id
                ),
                None,
            )
            if existing is not None:
                if (
                    existing["response"] == response_type
                    and existing["entry_id"] == entry_id
                    and existing["statement"] == statement
                ):
                    return self._view(protocol, scope)
                raise ExamProtocolConflictError(
                    "Für diesen Protokollstand wurde bereits anders reagiert"
                )
            handle = self._guard_day_mutation(
                work,
                protocol,
                "protocol_response",
                payload.get("expected_day_revision"),
                actor_id,
                protocol_revision_id=revision["id"],
            )
            work.write_protocol_response(
                {
                    "protocol_id": protocol_id,
                    "version": revision["version"],
                    "actor_member_id": actor_id,
                    "response": response_type,
                    "entry_id": entry_id,
                    "statement": statement,
                    "responded_at": self._now(),
                }
            )
            work.complete_day_mutation(
                handle,
                actor_member_id=actor_id,
                reason=statement,
                protocol_revision_id=revision["id"],
            )
            return self._view(self._required_protocol(work, protocol_id), scope)

    def request_correction(
        self,
        scope: AuthorizationScope,
        protocol_id: int,
        payload: ProtocolCorrectionRequestCommand,
    ) -> dict[str, Any]:
        expected_version = self._required_version(payload)
        reason = self._required_text(payload.get("reason"), "reason", 2000)
        with self._unit_of_work_factory(write=True) as work:
            protocol = self._required_protocol(work, protocol_id)
            actor_id, participants, _managed = self._require_access(protocol, scope, react=True)
            revision = self._current_revision(protocol)
            self._assert_version(revision, expected_version)
            if actor_id not in participants:
                raise PermissionError("Forbidden.")
            if self._state(protocol, revision) not in COMPLETE_STATES:
                raise ValueError(
                    "Ergänzungsbedarf kann erst nach vollständiger Reaktion gemeldet werden"
                )
            existing = next(
                (
                    item
                    for item in protocol["correction_requests"]
                    if item["revision_id"] == revision["id"]
                    and item["requested_by_member_id"] == actor_id
                    and item["reason"] == reason
                ),
                None,
            )
            if existing is None:
                handle = self._guard_day_mutation(
                    work,
                    protocol,
                    "protocol_correction_request",
                    payload.get("expected_day_revision"),
                    actor_id,
                )
                work.write_protocol_correction_request(
                    {
                        "protocol_id": protocol_id,
                        "revision_id": revision["id"],
                        "actor_member_id": actor_id,
                        "reason": reason,
                        "requested_at": self._now(),
                    }
                )
                work.complete_day_mutation(handle, actor_member_id=actor_id, reason=reason)
                protocol = self._required_protocol(work, protocol_id)
            return self._view(protocol, scope)

    def open_correction(
        self, scope: AuthorizationScope, protocol_id: int, payload: ProtocolCorrectionOpenCommand
    ) -> dict[str, Any]:
        expected_version = self._required_version(payload)
        reason = self._required_text(payload.get("reason"), "reason", 2000)
        raw_request_id = payload.get("correction_request_id")
        if not isinstance(raw_request_id, int) or isinstance(raw_request_id, bool):
            raise ValueError("Ein Korrekturvorgang benötigt einen Ergänzungsbedarf")
        with self._unit_of_work_factory(write=True) as work:
            protocol = self._required_protocol(work, protocol_id)
            actor_id, _participants, can_manage = self._require_access(protocol, scope, manage=True)
            if not can_manage or actor_id is None:
                raise PermissionError("Forbidden.")
            current = self._current_revision(protocol)
            if (
                current["version"] == expected_version + 1
                and current["correction_request_id"] == raw_request_id
                and current["workflow_state"] == "correction_open"
            ):
                return self._view(protocol, scope)
            self._assert_version(current, expected_version)
            if self._state(protocol, current) not in COMPLETE_STATES:
                raise ValueError("Nur ein vollständig behandelter Stand kann korrigiert werden")
            request = next(
                (item for item in protocol["correction_requests"] if item["id"] == raw_request_id),
                None,
            )
            if (
                request is None
                or request["revision_id"] != current["id"]
                or request["status"] != "pending"
            ):
                raise ValueError("Der Ergänzungsbedarf ist nicht mehr offen")
            reopening_reference = self._optional_text(payload.get("reopening_reference"), 500)
            if protocol["day_status"] == "completed" and reopening_reference is None:
                raise ValueError(
                    "Nach Tagesabschluss ist eine zulässige Wiederöffnung nach #36 erforderlich"
                )
            handle = self._guard_day_mutation(
                work,
                protocol,
                "exam_protocol",
                payload.get("expected_day_revision"),
                actor_id,
            )
            work.open_protocol_correction(
                {
                    "protocol_id": protocol_id,
                    "expected_version": current["version"],
                    "correction_request_id": request["id"],
                    "actor_member_id": actor_id,
                    "reason": reason,
                    "reopening_reference": reopening_reference,
                    "created_at": self._now(),
                }
            )
            work.complete_day_mutation(handle, actor_member_id=actor_id, reason=reason)
            return self._view(self._required_protocol(work, protocol_id), scope)

    def set_retention(
        self, scope: AuthorizationScope, protocol_id: int, payload: ProtocolRetentionCommand
    ) -> dict[str, Any]:
        rule_reference = self._required_text(payload.get("rule_reference"), "rule_reference", 1000)
        retain_until = self._optional_text(payload.get("retain_until"), 100)
        legal_hold = payload.get("legal_hold", False)
        if not isinstance(legal_hold, bool):
            raise ValueError("legal_hold muss ein boolescher Wert sein")
        hold_reason = self._optional_text(payload.get("hold_reason"), 2000)
        if legal_hold and hold_reason is None:
            raise ValueError("Eine Aufbewahrungssperre benötigt eine Begründung")
        with self._unit_of_work_factory(write=True) as work:
            protocol = self._required_protocol(work, protocol_id)
            actor_id, _participants, can_manage = self._require_access(protocol, scope, manage=True)
            if not can_manage or actor_id is None:
                raise PermissionError("Forbidden.")
            existing = protocol["retention"]
            if (
                existing is not None
                and existing["retain_until"] is not None
                and (retain_until is None or retain_until < existing["retain_until"])
            ):
                raise ValueError("Eine verbindliche Aufbewahrungsfrist darf nicht verkürzt werden")
            if existing is not None and existing["legal_hold"] and not legal_hold:
                release_reason = self._optional_text(payload.get("release_reason"), 2000)
                if release_reason is None:
                    raise ValueError("Das Aufheben einer Sperre benötigt eine Begründung")
                hold_reason = f"Freigabe: {release_reason}"
            work.save_protocol_retention(
                {
                    "protocol_id": protocol_id,
                    "rule_reference": rule_reference,
                    "retain_until": retain_until,
                    "legal_hold": legal_hold,
                    "hold_reason": hold_reason,
                    "actor_member_id": actor_id,
                    "updated_at": self._now(),
                }
            )
            return self._view(self._required_protocol(work, protocol_id), scope)

    def completion_for_day(self, scope: AuthorizationScope, day_id: int) -> dict[str, Any] | None:
        with self._unit_of_work_factory() as work:
            day = work.protocol_day_snapshot(day_id)
            if day is None:
                return None
            if not scope.can_read_committee(day["committee_id"]):
                raise PermissionError("Forbidden.")
            items: list[dict[str, Any]] = []
            for slot in day["slots"]:
                protocol = slot["protocol"]
                if slot["actual_started_at"] is None:
                    item = {
                        "exam_slot_id": slot["exam_slot_id"],
                        "required": False,
                        "state": "not_required",
                        "regular_close_ready": True,
                    }
                elif protocol is None and slot["execution_status"] == "completed":
                    item = {
                        "exam_slot_id": slot["exam_slot_id"],
                        "required": False,
                        "state": "legacy_missing",
                        "regular_close_ready": True,
                    }
                elif protocol is None:
                    item = {
                        "exam_slot_id": slot["exam_slot_id"],
                        "required": True,
                        "state": "missing",
                        "regular_close_ready": False,
                    }
                else:
                    current = self._current_revision(protocol)
                    state = self._state(protocol, current)
                    item = {
                        "exam_slot_id": slot["exam_slot_id"],
                        "exam_protocol_id": protocol["id"],
                        "required": True,
                        "state": state,
                        "regular_close_ready": state in COMPLETE_STATES,
                    }
                items.append(item)
            return {
                "exam_day_id": day["exam_day_id"],
                "slots": items,
                "regular_close_ready": all(item["regular_close_ready"] for item in items),
            }

    def machine_export(self, scope: AuthorizationScope, protocol_id: int) -> dict[str, Any]:
        with self._unit_of_work_factory() as work:
            protocol = self._required_protocol(work, protocol_id)
            self._require_access(protocol, scope)
            view = self._view(protocol, scope)
            references: ProtocolReferencesSnapshot = work.protocol_references(protocol_id)
            return {
                "export_version": 1,
                "complete": view["closing_ready"],
                "current_state": view["state"],
                "references": references,
                "protocol": view,
            }

    def _view(
        self, protocol: ExecutionProtocolSnapshot, scope: AuthorizationScope
    ) -> dict[str, Any]:
        actor_id, participants, can_manage = self._access(protocol, scope)
        revisions = list(protocol["revisions"])
        current = self._current_revision(protocol)
        state = self._state(protocol, current)
        content_mutable = protocol["day_closure_status"] == "open"
        if protocol["day_closure_status"] == "reopening":
            content_mutable = f"exam_protocol:{protocol['id']}" in protocol["reopening_scope"]
        late_response = (
            protocol["day_closure_status"] == "closed_exception"
            and actor_id is not None
            and actor_id in protocol["late_response_member_ids"]
        )
        return {
            "id": protocol["id"],
            "exam_slot_id": protocol["exam_slot_id"],
            "day_revision": protocol["day_revision"],
            "current_version": protocol["current_version"],
            "source": protocol["source"],
            "state": state,
            "closing_ready": state in COMPLETE_STATES,
            "participants": sorted(participants),
            "current_revision": self._revision_view(current, participants, obsolete=False),
            "history": [
                self._revision_view(
                    revision,
                    participants,
                    obsolete=revision["version"] != protocol["current_version"],
                )
                for revision in revisions
            ],
            "correction_requests": [dict(item) for item in protocol["correction_requests"]],
            "open_correction": current["workflow_state"] == "correction_open",
            "retention": (
                dict(protocol["retention"]) if protocol["retention"] is not None else None
            ),
            "permissions": {
                "edit": content_mutable
                and (
                    actor_id in participants
                    or (can_manage and current["workflow_state"] == "correction_open")
                ),
                "submit": content_mutable and actor_id in participants,
                "respond": (content_mutable or late_response) and actor_id in participants,
                "request_correction": actor_id in participants,
                "coordinate_correction": content_mutable and can_manage,
                "manage_retention": can_manage,
            },
            "created_at": protocol["created_at"],
            "updated_at": protocol["updated_at"],
        }

    @staticmethod
    def _revision_view(
        revision: ProtocolRevisionSnapshot,
        participants: set[int],
        *,
        obsolete: bool,
    ) -> dict[str, Any]:
        response_member_ids = {item["committee_member_id"] for item in revision["responses"]}
        return {
            "id": revision["id"],
            "version": revision["version"],
            "declaration": revision["declaration"],
            "workflow_state": revision["workflow_state"],
            "previous_revision_id": revision["previous_revision_id"],
            "correction_request_id": revision["correction_request_id"],
            "changed_by_member_id": revision["changed_by_member_id"],
            "change_reason": revision["change_reason"],
            "submitted_by_member_id": revision["submitted_by_member_id"],
            "submitted_at": revision["submitted_at"],
            "created_at": revision["created_at"],
            "obsolete": obsolete,
            "missing_response_member_ids": sorted(participants - response_member_ids),
            "entries": [
                {
                    "id": item["id"],
                    "category": item["category"],
                    "statement": item["statement"],
                    "occurred_from": item["occurred_from"],
                    "occurred_to": item["occurred_to"],
                    "recorded_by_member_id": item["recorded_by_member_id"],
                    "created_at": item["created_at"],
                }
                for item in revision["entries"]
            ],
            "responses": [dict(item) for item in revision["responses"]],
        }

    @staticmethod
    def _state(protocol: ExecutionProtocolSnapshot, revision: ProtocolRevisionSnapshot) -> str:
        if revision["workflow_state"] == "correction_open" and revision["submitted_at"] is None:
            return "correction_open"
        if revision["submitted_at"] is None:
            return "in_progress"
        responses = list(revision["responses"])
        if not responses:
            return "awaiting_confirmation"
        if {item["committee_member_id"] for item in responses} != set(protocol["participants"]):
            return "reaction_missing"
        return (
            "fully_with_reservation"
            if any(item["response"] == "reservation" for item in responses)
            else "fully_confirmed"
        )

    def _require_access(
        self,
        protocol: ExecutionProtocolSnapshot,
        scope: AuthorizationScope,
        *,
        edit: bool = False,
        react: bool = False,
        manage: bool = False,
    ) -> tuple[int | None, set[int], bool]:
        actor_id, participants, can_manage = self._access(protocol, scope)
        if actor_id not in participants and not can_manage:
            raise PermissionError("Forbidden.")
        if react and actor_id not in participants:
            raise PermissionError("Forbidden.")
        if manage and not can_manage:
            raise PermissionError("Forbidden.")
        if edit and actor_id is None:
            raise PermissionError("Forbidden.")
        return actor_id, participants, can_manage

    @staticmethod
    def _access(
        protocol: ExecutionProtocolSnapshot, scope: AuthorizationScope
    ) -> tuple[int | None, set[int], bool]:
        committee_id = protocol["committee_id"]
        return (
            scope.member_for_committee(committee_id),
            set(protocol["participants"]),
            scope.can_manage_committee(committee_id),
        )

    def _required_protocol(
        self, work: ExecutionProtocolUnitOfWork, protocol_id: int
    ) -> ExecutionProtocolSnapshot:
        protocol = work.protocol_by_id(protocol_id)
        if protocol is None:
            raise ValueError("Prüfungsprotokoll nicht gefunden")
        return protocol

    @staticmethod
    def _current_revision(protocol: ExecutionProtocolSnapshot) -> ProtocolRevisionSnapshot:
        revision = next(
            (
                item
                for item in protocol["revisions"]
                if item["version"] == protocol["current_version"]
            ),
            None,
        )
        if revision is None:
            raise RuntimeError("Aktueller Protokollstand fehlt")
        return revision

    def _revision_content(
        self, revision: ProtocolRevisionSnapshot
    ) -> tuple[str | None, list[dict[str, str | None]]]:
        return (
            revision["declaration"],
            [
                {
                    "category": item["category"],
                    "statement": item["statement"],
                    "occurred_from": item["occurred_from"],
                    "occurred_to": item["occurred_to"],
                }
                for item in revision["entries"]
            ],
        )

    def _response_details(
        self,
        revision: ProtocolRevisionSnapshot,
        response_type: str,
        payload: ProtocolResponseCommand,
    ) -> tuple[int | None, str | None]:
        entry_id: int | None = None
        statement: str | None = None
        if response_type == "reservation":
            raw_entry_id = payload.get("entry_id")
            if raw_entry_id is not None:
                if not isinstance(raw_entry_id, int) or isinstance(raw_entry_id, bool):
                    raise ValueError("Ungültige betroffene Protokollstelle")
                entry = next(
                    (item for item in revision["entries"] if item["id"] == raw_entry_id), None
                )
                if entry is None:
                    raise ValueError(
                        "Die betroffene Protokollstelle gehört nicht zum aktuellen Stand"
                    )
                entry_id = entry["id"]
            statement = self._required_text(payload.get("statement"), "statement", 2000)
        elif payload.get("entry_id") is not None or payload.get("statement") is not None:
            raise ValueError("Eine Bestätigung enthält keinen Vorbehaltstext")
        return entry_id, statement

    def _normalize_content(
        self, payload: ProtocolContentCommand
    ) -> tuple[str, list[ProtocolEntryDraft]]:
        declaration = payload.get("declaration")
        if declaration not in DECLARATIONS:
            raise ValueError("Der Prüfungsverlauf muss ausdrücklich festgestellt werden")
        raw_entries = payload.get("entries", [])
        if not isinstance(raw_entries, list):
            raise ValueError("Protokolleinträge müssen als Liste übermittelt werden")
        entries: list[ProtocolEntryDraft] = []
        for raw_entry in raw_entries:
            if not isinstance(raw_entry, dict) or set(raw_entry) - ENTRY_FIELDS:
                raise ValueError("Ein Protokolleintrag enthält unzulässige Felder")
            category = raw_entry.get("category")
            if category not in ENTRY_CATEGORIES:
                raise ValueError("Unbekannte Kategorie für eine Besonderheit")
            occurred_from = self._required_text(
                raw_entry.get("occurred_from"), "occurred_from", 100
            )
            occurred_to = self._optional_text(raw_entry.get("occurred_to"), 100)
            if occurred_to is not None and occurred_to < occurred_from:
                raise ValueError("Das Ende eines Zeitraums darf nicht vor seinem Beginn liegen")
            entries.append(
                {
                    "category": category,
                    "statement": self._required_text(raw_entry.get("statement"), "statement", 2000),
                    "occurred_from": occurred_from,
                    "occurred_to": occurred_to,
                }
            )
        if declaration == "without_special_occurrences" and entries:
            raise ValueError("Ein regulärer Verlauf enthält keine Besonderheiten")
        if declaration == "with_special_occurrences" and not entries:
            raise ValueError("Ein abweichender Verlauf benötigt mindestens eine Besonderheit")
        return declaration, entries

    @staticmethod
    def _validate_persisted_content(revision: ProtocolRevisionSnapshot) -> None:
        if revision["declaration"] not in DECLARATIONS:
            raise ValueError("Der Prüfungsverlauf wurde noch nicht festgestellt")
        if revision["declaration"] == "without_special_occurrences" and revision["entries"]:
            raise ValueError("Ein regulärer Verlauf enthält keine Besonderheiten")
        if revision["declaration"] == "with_special_occurrences" and not revision["entries"]:
            raise ValueError("Ein abweichender Verlauf benötigt mindestens eine Besonderheit")

    @staticmethod
    def _required_version(payload: ProtocolVersionCommand) -> int:
        version = payload.get("version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ValueError("Eine gültige Protokollversion ist erforderlich")
        return version

    @staticmethod
    def _assert_version(revision: ProtocolRevisionSnapshot, expected_version: int) -> None:
        if revision["version"] != expected_version:
            raise ExamProtocolConflictError("Der Protokollstand wurde zwischenzeitlich geändert")

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

    def _guard_day_mutation(
        self,
        work: ExecutionProtocolUnitOfWork,
        protocol: ExecutionProtocolSnapshot,
        kind: str,
        expected_day_revision: object | None,
        actor_member_id: int,
        *,
        protocol_revision_id: int | None = None,
    ) -> int:
        if protocol["exam_day_id"] is None:
            raise ValueError("Der Prüfungstag zum Protokoll fehlt")
        request: DayMutationRequest = {
            "day_id": protocol["exam_day_id"],
            "kind": kind,
            "entity_id": protocol["id"],
            "expected_day_revision": expected_day_revision,
            "actor_member_id": actor_member_id,
            "protocol_revision_id": protocol_revision_id,
        }
        return work.guard_day_mutation(request)

    def _now(self) -> str:
        return self._clock()
