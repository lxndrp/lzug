"""Versioned, jointly confirmed protocols for exams that actually started."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .authorization import AuthorizationScope
from .database import DEFAULT_DB_PATH, session_scope
from .exam_day_closures import (
    complete_day_mutation,
    day_for_protocol,
    guard_day_mutation,
)
from .models import (
    Candidate,
    CandidateExamAttendance,
    CommitteeMember,
    ExamDay,
    ExamDayReopening,
    ExamDayTask,
    ExamProtocol,
    ExamProtocolCorrectionRequest,
    ExamProtocolEntry,
    ExamProtocolParticipant,
    ExamProtocolResponse,
    ExamProtocolRetention,
    ExamProtocolRevision,
    ExamResult,
    ExamRoom,
    ExamRound,
    ExamSlot,
    ExamVenue,
    MemberExamAttendance,
    Person,
    RoundCandidate,
)

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


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def create_protocol_for_started_slot(
    session: Session,
    *,
    slot_id: int,
    participant_member_ids: set[int],
    created_by_member_id: int | None,
    created_at: str,
    source: str = "application",
) -> ExamProtocol:
    """Create the protocol and participant snapshot in the slot-start transaction."""
    existing = session.scalar(select(ExamProtocol).where(ExamProtocol.exam_slot_id == slot_id))
    if existing is not None:
        return existing
    if not participant_member_ids:
        raise ValueError("Ein Prüfungsprotokoll benötigt tatsächlich beteiligte Prüfer")
    protocol = ExamProtocol(
        exam_slot_id=slot_id,
        current_version=1,
        created_by_member_id=created_by_member_id,
        source=source,
        created_at=created_at,
        updated_at=created_at,
    )
    session.add(protocol)
    session.flush()
    session.add_all(
        ExamProtocolParticipant(
            exam_protocol_id=protocol.id,
            committee_member_id=member_id,
            created_at=created_at,
        )
        for member_id in sorted(participant_member_ids)
    )
    session.add(
        ExamProtocolRevision(
            exam_protocol_id=protocol.id,
            version=1,
            workflow_state="draft",
            changed_by_member_id=created_by_member_id,
            change_reason="exam_started",
            created_at=created_at,
        )
    )
    session.flush()
    return protocol


class ExamProtocolService:
    """Apply protocol state, access, history, retention, and export contracts."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path

    def get_by_slot(self, scope: AuthorizationScope, slot_id: int) -> dict[str, Any] | None:
        with session_scope(self.db_path) as session:
            protocol = session.scalar(
                select(ExamProtocol).where(ExamProtocol.exam_slot_id == slot_id)
            )
            if protocol is None:
                return None
            self._require_access(session, protocol, scope)
            return self._view(session, protocol, scope)

    def get(self, scope: AuthorizationScope, protocol_id: int) -> dict[str, Any] | None:
        with session_scope(self.db_path) as session:
            protocol = session.get(ExamProtocol, protocol_id)
            if protocol is None:
                return None
            self._require_access(session, protocol, scope)
            return self._view(session, protocol, scope)

    def update_content(
        self, scope: AuthorizationScope, protocol_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        declaration, entries = self._normalize_content(payload)
        expected_version = self._required_version(payload)
        with session_scope(self.db_path) as session:
            protocol = self._required_protocol(session, protocol_id)
            actor_id, _participants, can_manage = self._require_access(
                session, protocol, scope, edit=True
            )
            current = self._current_revision(session, protocol)
            if current.version != expected_version:
                if (
                    current.previous_revision_id is not None
                    and current.version == expected_version + 1
                    and self._revision_content(session, current) == (declaration, entries)
                ):
                    return self._view(session, protocol, scope)
                raise ExamProtocolConflictError(
                    "Der Protokollstand wurde zwischenzeitlich geändert"
                )
            state = self._state(session, protocol, current)
            if state in COMPLETE_STATES:
                raise ExamProtocolConflictError(
                    "Ein vollständig behandelter Stand benötigt einen Korrekturvorgang"
                )
            if actor_id is None or (
                actor_id not in self._participant_ids(session, protocol)
                and not (can_manage and current.workflow_state == "correction_open")
            ):
                raise PermissionError("Forbidden.")

            day = day_for_protocol(session, protocol.id)
            if day is None:
                raise ValueError("Der Prüfungstag zum Protokoll fehlt")
            day_guard = guard_day_mutation(
                session,
                day=day,
                kind="exam_protocol",
                entity_id=protocol.id,
                payload=payload,
                actor_member_id=actor_id,
            )

            created_at = _now()
            revision = ExamProtocolRevision(
                exam_protocol_id=protocol.id,
                version=current.version + 1,
                declaration=declaration,
                workflow_state=(
                    "correction_open" if current.workflow_state == "correction_open" else "draft"
                ),
                previous_revision_id=current.id,
                correction_request_id=current.correction_request_id,
                changed_by_member_id=actor_id,
                change_reason=self._optional_text(payload.get("change_reason"), 1000),
                created_at=created_at,
            )
            session.add(revision)
            session.flush()
            for entry in entries:
                session.add(
                    ExamProtocolEntry(
                        exam_protocol_revision_id=revision.id,
                        category=entry["category"],
                        statement=entry["statement"],
                        occurred_from=entry["occurred_from"],
                        occurred_to=entry["occurred_to"],
                        recorded_by_member_id=actor_id,
                        created_at=created_at,
                    )
                )
            protocol.current_version = revision.version
            protocol.updated_at = created_at
            session.flush()
            complete_day_mutation(
                session,
                day_guard,
                actor_member_id=actor_id,
                reason=revision.change_reason,
            )
            return self._view(session, protocol, scope)

    def submit(
        self, scope: AuthorizationScope, protocol_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        expected_version = self._required_version(payload)
        with session_scope(self.db_path) as session:
            protocol = self._required_protocol(session, protocol_id)
            actor_id, participants, _managed = self._require_access(
                session, protocol, scope, react=True
            )
            revision = self._current_revision(session, protocol)
            self._assert_version(revision, expected_version)
            if revision.submitted_at is not None:
                return self._view(session, protocol, scope)
            if actor_id not in participants:
                raise PermissionError("Forbidden.")
            day = day_for_protocol(session, protocol.id)
            if day is None:
                raise ValueError("Der Prüfungstag zum Protokoll fehlt")
            day_guard = guard_day_mutation(
                session,
                day=day,
                kind="exam_protocol",
                entity_id=protocol.id,
                payload=payload,
                actor_member_id=actor_id,
            )
            self._validate_persisted_content(session, revision)
            revision.workflow_state = "submitted"
            revision.submitted_by_member_id = actor_id
            revision.submitted_at = _now()
            protocol.updated_at = revision.submitted_at
            session.flush()
            complete_day_mutation(session, day_guard, actor_member_id=actor_id)
            return self._view(session, protocol, scope)

    def respond(
        self, scope: AuthorizationScope, protocol_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        expected_version = self._required_version(payload)
        response_type = payload.get("response")
        if response_type not in RESPONSE_TYPES:
            raise ValueError("Unbekannte Protokollreaktion")
        with session_scope(self.db_path) as session:
            protocol = self._required_protocol(session, protocol_id)
            actor_id, participants, _managed = self._require_access(
                session, protocol, scope, react=True
            )
            revision = self._current_revision(session, protocol)
            self._assert_version(revision, expected_version)
            if revision.submitted_at is None:
                raise ValueError("Das Protokoll wurde noch nicht zur Bestätigung vorgelegt")
            if actor_id not in participants:
                raise PermissionError("Forbidden.")

            entry_id: int | None = None
            statement: str | None = None
            if response_type == "reservation":
                raw_entry_id = payload.get("entry_id")
                if raw_entry_id is not None:
                    if not isinstance(raw_entry_id, int) or isinstance(raw_entry_id, bool):
                        raise ValueError("Ungültige betroffene Protokollstelle")
                    entry = session.get(ExamProtocolEntry, raw_entry_id)
                    if entry is None or entry.exam_protocol_revision_id != revision.id:
                        raise ValueError(
                            "Die betroffene Protokollstelle gehört nicht zum aktuellen Stand"
                        )
                    entry_id = entry.id
                statement = self._required_text(payload.get("statement"), "statement", 2000)
            elif payload.get("entry_id") is not None or payload.get("statement") is not None:
                raise ValueError("Eine Bestätigung enthält keinen Vorbehaltstext")

            existing = session.scalar(
                select(ExamProtocolResponse).where(
                    ExamProtocolResponse.exam_protocol_revision_id == revision.id,
                    ExamProtocolResponse.committee_member_id == actor_id,
                )
            )
            if existing is not None:
                if (
                    existing.response == response_type
                    and existing.exam_protocol_entry_id == entry_id
                    and existing.statement == statement
                ):
                    return self._view(session, protocol, scope)
                raise ExamProtocolConflictError(
                    "Für diesen Protokollstand wurde bereits anders reagiert"
                )
            day = day_for_protocol(session, protocol.id)
            if day is None:
                raise ValueError("Der Prüfungstag zum Protokoll fehlt")
            day_guard = guard_day_mutation(
                session,
                day=day,
                kind="protocol_response",
                entity_id=protocol.id,
                payload=payload,
                actor_member_id=actor_id,
                protocol_revision_id=revision.id,
            )
            session.add(
                ExamProtocolResponse(
                    exam_protocol_revision_id=revision.id,
                    committee_member_id=actor_id,
                    response=response_type,
                    exam_protocol_entry_id=entry_id,
                    statement=statement,
                    responded_at=_now(),
                )
            )
            session.flush()
            complete_day_mutation(
                session,
                day_guard,
                actor_member_id=actor_id,
                reason=statement,
                protocol_revision_id=revision.id,
            )
            return self._view(session, protocol, scope)

    def request_correction(
        self, scope: AuthorizationScope, protocol_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        expected_version = self._required_version(payload)
        reason = self._required_text(payload.get("reason"), "reason", 2000)
        with session_scope(self.db_path) as session:
            protocol = self._required_protocol(session, protocol_id)
            actor_id, participants, _managed = self._require_access(
                session, protocol, scope, react=True
            )
            revision = self._current_revision(session, protocol)
            self._assert_version(revision, expected_version)
            if actor_id not in participants:
                raise PermissionError("Forbidden.")
            if self._state(session, protocol, revision) not in COMPLETE_STATES:
                raise ValueError(
                    "Ergänzungsbedarf kann erst nach vollständiger Reaktion gemeldet werden"
                )
            existing = session.scalar(
                select(ExamProtocolCorrectionRequest).where(
                    ExamProtocolCorrectionRequest.exam_protocol_id == protocol.id,
                    ExamProtocolCorrectionRequest.exam_protocol_revision_id == revision.id,
                    ExamProtocolCorrectionRequest.requested_by_member_id == actor_id,
                    ExamProtocolCorrectionRequest.reason == reason,
                )
            )
            if existing is None:
                day = day_for_protocol(session, protocol.id)
                if day is None:
                    raise ValueError("Der Prüfungstag zum Protokoll fehlt")
                day_guard = guard_day_mutation(
                    session,
                    day=day,
                    kind="protocol_correction_request",
                    entity_id=protocol.id,
                    payload=payload,
                    actor_member_id=actor_id,
                )
                session.add(
                    ExamProtocolCorrectionRequest(
                        exam_protocol_id=protocol.id,
                        exam_protocol_revision_id=revision.id,
                        requested_by_member_id=actor_id,
                        reason=reason,
                        status="pending",
                        requested_at=_now(),
                    )
                )
                session.flush()
                complete_day_mutation(
                    session,
                    day_guard,
                    actor_member_id=actor_id,
                    reason=reason,
                )
            return self._view(session, protocol, scope)

    def open_correction(
        self, scope: AuthorizationScope, protocol_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        expected_version = self._required_version(payload)
        reason = self._required_text(payload.get("reason"), "reason", 2000)
        raw_request_id = payload.get("correction_request_id")
        if not isinstance(raw_request_id, int) or isinstance(raw_request_id, bool):
            raise ValueError("Ein Korrekturvorgang benötigt einen Ergänzungsbedarf")
        with session_scope(self.db_path) as session:
            protocol = self._required_protocol(session, protocol_id)
            actor_id, _participants, can_manage = self._require_access(
                session, protocol, scope, manage=True
            )
            if not can_manage or actor_id is None:
                raise PermissionError("Forbidden.")
            current = self._current_revision(session, protocol)
            if (
                current.version == expected_version + 1
                and current.correction_request_id == raw_request_id
                and current.workflow_state == "correction_open"
            ):
                return self._view(session, protocol, scope)
            self._assert_version(current, expected_version)
            if self._state(session, protocol, current) not in COMPLETE_STATES:
                raise ValueError("Nur ein vollständig behandelter Stand kann korrigiert werden")
            day = day_for_protocol(session, protocol.id)
            if day is None:
                raise ValueError("Der Prüfungstag zum Protokoll fehlt")
            day_guard = guard_day_mutation(
                session,
                day=day,
                kind="exam_protocol",
                entity_id=protocol.id,
                payload=payload,
                actor_member_id=actor_id,
            )
            request = session.get(ExamProtocolCorrectionRequest, raw_request_id)
            if (
                request is None
                or request.exam_protocol_id != protocol.id
                or request.exam_protocol_revision_id != current.id
                or request.status != "pending"
            ):
                raise ValueError("Der Ergänzungsbedarf ist nicht mehr offen")
            slot = session.get(ExamSlot, protocol.exam_slot_id)
            day = session.get(ExamDay, slot.exam_day_id) if slot else None
            reopening_reference = self._optional_text(payload.get("reopening_reference"), 500)
            if day is not None and day.status == "completed" and reopening_reference is None:
                raise ValueError(
                    "Nach Tagesabschluss ist eine zulässige Wiederöffnung nach #36 erforderlich"
                )

            created_at = _now()
            revision = ExamProtocolRevision(
                exam_protocol_id=protocol.id,
                version=current.version + 1,
                declaration=current.declaration,
                workflow_state="correction_open",
                previous_revision_id=current.id,
                correction_request_id=request.id,
                changed_by_member_id=actor_id,
                change_reason=reason,
                created_at=created_at,
            )
            session.add(revision)
            session.flush()
            for entry in self._entries(session, current):
                session.add(
                    ExamProtocolEntry(
                        exam_protocol_revision_id=revision.id,
                        category=entry.category,
                        statement=entry.statement,
                        occurred_from=entry.occurred_from,
                        occurred_to=entry.occurred_to,
                        recorded_by_member_id=entry.recorded_by_member_id,
                        created_at=entry.created_at,
                    )
                )
            request.status = "opened"
            request.opened_by_member_id = actor_id
            request.opened_at = created_at
            request.reopening_reference = reopening_reference
            protocol.current_version = revision.version
            protocol.updated_at = created_at
            session.flush()
            complete_day_mutation(
                session,
                day_guard,
                actor_member_id=actor_id,
                reason=reason,
            )
            return self._view(session, protocol, scope)

    def set_retention(
        self, scope: AuthorizationScope, protocol_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        rule_reference = self._required_text(payload.get("rule_reference"), "rule_reference", 1000)
        retain_until = self._optional_text(payload.get("retain_until"), 100)
        legal_hold = payload.get("legal_hold", False)
        if not isinstance(legal_hold, bool):
            raise ValueError("legal_hold muss ein boolescher Wert sein")
        hold_reason = self._optional_text(payload.get("hold_reason"), 2000)
        if legal_hold and hold_reason is None:
            raise ValueError("Eine Aufbewahrungssperre benötigt eine Begründung")
        with session_scope(self.db_path) as session:
            protocol = self._required_protocol(session, protocol_id)
            actor_id, _participants, can_manage = self._require_access(
                session, protocol, scope, manage=True
            )
            if not can_manage or actor_id is None:
                raise PermissionError("Forbidden.")
            existing = session.scalar(
                select(ExamProtocolRetention).where(
                    ExamProtocolRetention.exam_protocol_id == protocol.id
                )
            )
            if (
                existing is not None
                and existing.retain_until is not None
                and (retain_until is None or retain_until < existing.retain_until)
            ):
                raise ValueError("Eine verbindliche Aufbewahrungsfrist darf nicht verkürzt werden")
            if existing is not None and bool(existing.legal_hold) and not legal_hold:
                release_reason = self._optional_text(payload.get("release_reason"), 2000)
                if release_reason is None:
                    raise ValueError("Das Aufheben einer Sperre benötigt eine Begründung")
                hold_reason = f"Freigabe: {release_reason}"
            if existing is None:
                session.add(
                    ExamProtocolRetention(
                        exam_protocol_id=protocol.id,
                        rule_reference=rule_reference,
                        retain_until=retain_until,
                        legal_hold=int(legal_hold),
                        hold_reason=hold_reason,
                        updated_by_member_id=actor_id,
                        updated_at=_now(),
                    )
                )
            else:
                existing.rule_reference = rule_reference
                existing.retain_until = retain_until
                existing.legal_hold = int(legal_hold)
                existing.hold_reason = hold_reason
                existing.updated_by_member_id = actor_id
                existing.updated_at = _now()
            session.flush()
            return self._view(session, protocol, scope)

    def completion_for_day(self, scope: AuthorizationScope, day_id: int) -> dict[str, Any] | None:
        with session_scope(self.db_path) as session:
            day = session.get(ExamDay, day_id)
            if day is None:
                return None
            exam_round = session.get(ExamRound, day.exam_round_id)
            if exam_round is None or not scope.can_read_committee(exam_round.committee_id):
                raise PermissionError("Forbidden.")
            items: list[dict[str, Any]] = []
            for slot in session.scalars(
                select(ExamSlot).where(ExamSlot.exam_day_id == day.id).order_by(ExamSlot.id)
            ):
                protocol = session.scalar(
                    select(ExamProtocol).where(ExamProtocol.exam_slot_id == slot.id)
                )
                if slot.actual_started_at is None:
                    item = {
                        "exam_slot_id": slot.id,
                        "required": False,
                        "state": "not_required",
                        "regular_close_ready": True,
                    }
                elif protocol is None and slot.execution_status == "completed":
                    item = {
                        "exam_slot_id": slot.id,
                        "required": False,
                        "state": "legacy_missing",
                        "regular_close_ready": True,
                    }
                elif protocol is None:
                    item = {
                        "exam_slot_id": slot.id,
                        "required": True,
                        "state": "missing",
                        "regular_close_ready": False,
                    }
                else:
                    revision = self._current_revision(session, protocol)
                    state = self._state(session, protocol, revision)
                    item = {
                        "exam_slot_id": slot.id,
                        "exam_protocol_id": protocol.id,
                        "required": True,
                        "state": state,
                        "regular_close_ready": state in COMPLETE_STATES,
                    }
                items.append(item)
            return {
                "exam_day_id": day.id,
                "slots": items,
                "regular_close_ready": all(item["regular_close_ready"] for item in items),
            }

    def machine_export(self, scope: AuthorizationScope, protocol_id: int) -> dict[str, Any]:
        with session_scope(self.db_path) as session:
            protocol = self._required_protocol(session, protocol_id)
            self._require_access(session, protocol, scope)
            view = self._view(session, protocol, scope)
            return {
                "export_version": 1,
                "complete": view["closing_ready"],
                "current_state": view["state"],
                "references": self._references(session, protocol),
                "protocol": view,
            }

    def human_export(self, scope: AuthorizationScope, protocol_id: int) -> str:
        export = self.machine_export(scope, protocol_id)
        protocol = export["protocol"]
        references = export["references"]
        current = protocol["current_revision"]
        marker = "VOLLSTÄNDIG" if export["complete"] else "UNVOLLSTÄNDIG"
        candidate_name = (
            f"{references['candidate']['first_name']} {references['candidate']['last_name']}"
        )
        actual_completed_at = references["slot"]["actual_completed_at"] or "nicht erfasst"
        lines = [
            f"Prüfungsprotokoll {protocol['id']} – {marker}",
            f"Status: {protocol['state']}",
            f"Prüfling: {candidate_name}",
            f"IHK-Prüfungsnummer: {references['candidate']['ihk_exam_number']}",
            f"Prüfungsslot: {references['slot']['starts_at']} bis {references['slot']['ends_at']}",
            f"Tatsächlicher Beginn: {references['slot']['actual_started_at']}",
            f"Tatsächlicher Abschluss: {actual_completed_at}",
            f"Ort: {references['location']['name']} / {references['location']['room']}",
            "",
            "Tatsächlich beteiligte Prüfer:",
        ]
        lines.extend(
            f"- {person['first_name']} {person['last_name']} ({person['attendance']['status']})"
            for person in references["participants"]
        )
        lines.extend(["", f"Verlauf: {current['declaration'] or 'noch nicht festgestellt'}"])
        if current["entries"]:
            lines.append("Besonderheiten:")
            lines.extend(
                f"- [{entry['category']}] {entry['occurred_from']}"
                f"{(' bis ' + entry['occurred_to']) if entry['occurred_to'] else ''}: "
                f"{entry['statement']}"
                for entry in current["entries"]
            )
        lines.append("Reaktionen:")
        if current["responses"]:
            lines.extend(
                f"- Mitglied {response['committee_member_id']}: {response['response']}"
                f"{(': ' + response['statement']) if response['statement'] else ''}"
                for response in current["responses"]
            )
        else:
            lines.append("- keine")
        if protocol["open_correction"]:
            lines.append("Korrekturvorgang: offen")
        return "\n".join(lines) + "\n"

    def _view(
        self, session: Session, protocol: ExamProtocol, scope: AuthorizationScope
    ) -> dict[str, Any]:
        actor_id, participants, can_manage = self._access(session, protocol, scope)
        revisions = list(
            session.scalars(
                select(ExamProtocolRevision)
                .where(ExamProtocolRevision.exam_protocol_id == protocol.id)
                .order_by(ExamProtocolRevision.version)
            )
        )
        current = next(item for item in revisions if item.version == protocol.current_version)
        state = self._state(session, protocol, current)
        day = day_for_protocol(session, protocol.id)
        content_mutable = day is not None and day.closure_status == "open"
        if day is not None and day.closure_status == "reopening":
            reopening = session.scalar(
                select(ExamDayReopening).where(
                    ExamDayReopening.exam_day_id == day.id,
                    ExamDayReopening.status == "open",
                )
            )
            content_mutable = reopening is not None and f"exam_protocol:{protocol.id}" in set(
                json.loads(reopening.scope_json)
            )
        late_response = (
            day is not None
            and day.closure_status == "closed_exception"
            and actor_id is not None
            and session.scalar(
                select(ExamDayTask.id).where(
                    ExamDayTask.exam_day_id == day.id,
                    ExamDayTask.task_type == "protocol_follow_up",
                    ExamDayTask.recipient_member_id == actor_id,
                    ExamDayTask.exam_protocol_revision_id == current.id,
                    ExamDayTask.status == "open",
                )
            )
            is not None
        )
        correction_requests = list(
            session.scalars(
                select(ExamProtocolCorrectionRequest)
                .where(ExamProtocolCorrectionRequest.exam_protocol_id == protocol.id)
                .order_by(ExamProtocolCorrectionRequest.id)
            )
        )
        retention = session.scalar(
            select(ExamProtocolRetention).where(
                ExamProtocolRetention.exam_protocol_id == protocol.id
            )
        )
        return {
            "id": protocol.id,
            "exam_slot_id": protocol.exam_slot_id,
            "day_revision": day.revision if day is not None else None,
            "current_version": protocol.current_version,
            "source": protocol.source,
            "state": state,
            "closing_ready": state in COMPLETE_STATES,
            "participants": sorted(participants),
            "current_revision": self._revision_view(session, current, participants, obsolete=False),
            "history": [
                self._revision_view(
                    session,
                    revision,
                    participants,
                    obsolete=revision.version != protocol.current_version,
                )
                for revision in revisions
            ],
            "correction_requests": [
                {
                    "id": item.id,
                    "version": session.get(
                        ExamProtocolRevision, item.exam_protocol_revision_id
                    ).version,
                    "requested_by_member_id": item.requested_by_member_id,
                    "reason": item.reason,
                    "status": item.status,
                    "requested_at": item.requested_at,
                    "opened_by_member_id": item.opened_by_member_id,
                    "opened_at": item.opened_at,
                    "reopening_reference": item.reopening_reference,
                }
                for item in correction_requests
            ],
            "open_correction": current.workflow_state == "correction_open",
            "retention": (
                {
                    "rule_reference": retention.rule_reference,
                    "retain_until": retention.retain_until,
                    "legal_hold": bool(retention.legal_hold),
                    "hold_reason": retention.hold_reason,
                    "updated_by_member_id": retention.updated_by_member_id,
                    "updated_at": retention.updated_at,
                }
                if retention
                else None
            ),
            "permissions": {
                "edit": content_mutable
                and (
                    actor_id in participants
                    or (can_manage and current.workflow_state == "correction_open")
                ),
                "submit": content_mutable and actor_id in participants,
                "respond": (content_mutable or late_response) and actor_id in participants,
                "request_correction": actor_id in participants,
                "coordinate_correction": content_mutable and can_manage,
                "manage_retention": can_manage,
            },
            "created_at": protocol.created_at,
            "updated_at": protocol.updated_at,
            "_links": {
                "self": {"href": f"/api/exam-protocols/{protocol.id}"},
                "machine_export": {"href": f"/api/exam-protocols/{protocol.id}/export.json"},
                "human_export": {"href": f"/api/exam-protocols/{protocol.id}/export.txt"},
            },
        }

    def _revision_view(
        self,
        session: Session,
        revision: ExamProtocolRevision,
        participants: set[int],
        *,
        obsolete: bool,
    ) -> dict[str, Any]:
        entries = self._entries(session, revision)
        responses = list(
            session.scalars(
                select(ExamProtocolResponse)
                .where(ExamProtocolResponse.exam_protocol_revision_id == revision.id)
                .order_by(ExamProtocolResponse.id)
            )
        )
        response_member_ids = {item.committee_member_id for item in responses}
        return {
            "id": revision.id,
            "version": revision.version,
            "declaration": revision.declaration,
            "workflow_state": revision.workflow_state,
            "previous_revision_id": revision.previous_revision_id,
            "correction_request_id": revision.correction_request_id,
            "changed_by_member_id": revision.changed_by_member_id,
            "change_reason": revision.change_reason,
            "submitted_by_member_id": revision.submitted_by_member_id,
            "submitted_at": revision.submitted_at,
            "created_at": revision.created_at,
            "obsolete": obsolete,
            "missing_response_member_ids": sorted(participants - response_member_ids),
            "entries": [
                {
                    "id": item.id,
                    "category": item.category,
                    "statement": item.statement,
                    "occurred_from": item.occurred_from,
                    "occurred_to": item.occurred_to,
                    "recorded_by_member_id": item.recorded_by_member_id,
                    "created_at": item.created_at,
                }
                for item in entries
            ],
            "responses": [
                {
                    "id": item.id,
                    "committee_member_id": item.committee_member_id,
                    "response": item.response,
                    "entry_id": item.exam_protocol_entry_id,
                    "statement": item.statement,
                    "responded_at": item.responded_at,
                }
                for item in responses
            ],
        }

    def _references(self, session: Session, protocol: ExamProtocol) -> dict[str, Any]:
        slot = session.get(ExamSlot, protocol.exam_slot_id)
        day = session.get(ExamDay, slot.exam_day_id)
        exam_round = session.get(ExamRound, day.exam_round_id)
        round_candidate = session.get(RoundCandidate, slot.round_candidate_id)
        candidate = session.get(Candidate, round_candidate.candidate_id)
        room = session.get(ExamRoom, day.room_id)
        venue = session.get(ExamVenue, room.venue_id) if room else None
        candidate_attendance = session.scalar(
            select(CandidateExamAttendance).where(CandidateExamAttendance.exam_slot_id == slot.id)
        )
        participant_rows = list(
            session.scalars(
                select(ExamProtocolParticipant)
                .where(ExamProtocolParticipant.exam_protocol_id == protocol.id)
                .order_by(ExamProtocolParticipant.committee_member_id)
            )
        )
        participant_references = []
        for participant in participant_rows:
            member = session.get(CommitteeMember, participant.committee_member_id)
            person = session.get(Person, member.person_id)
            attendance = session.scalar(
                select(MemberExamAttendance).where(
                    MemberExamAttendance.exam_day_id == day.id,
                    MemberExamAttendance.committee_member_id == member.id,
                )
            )
            participant_references.append(
                {
                    "committee_member_id": member.id,
                    "first_name": person.first_name,
                    "last_name": person.last_name,
                    "representing_side": member.representing_side,
                    "attendance": {
                        "status": attendance.status if attendance else "open",
                        "arrived_at": attendance.arrived_at if attendance else None,
                    },
                }
            )
        result = session.scalar(
            select(ExamResult).where(ExamResult.round_candidate_id == round_candidate.id)
        )
        return {
            "candidate": {
                "id": candidate.id,
                "first_name": candidate.first_name,
                "last_name": candidate.last_name,
                "ihk_exam_number": candidate.ihk_exam_number,
            },
            "round": {"id": exam_round.id, "name": exam_round.name},
            "day": {"id": day.id, "date": day.date},
            "slot": {
                "id": slot.id,
                "slot_type": slot.slot_type,
                "starts_at": slot.starts_at,
                "ends_at": slot.ends_at,
                "actual_started_at": slot.actual_started_at,
                "actual_completed_at": slot.actual_completed_at,
                "execution_status": slot.execution_status,
            },
            "candidate_attendance": {
                "status": candidate_attendance.status if candidate_attendance else "open",
                "arrived_at": candidate_attendance.arrived_at if candidate_attendance else None,
            },
            "location": {
                "id": venue.id if venue else None,
                "name": venue.name if venue else "",
                "room": room.name if room else "",
                "city": venue.city if venue else "",
            },
            "participants": participant_references,
            "assessment": {
                "available": result is not None and result.legacy_status is None,
                "exam_result_id": result.id if result else None,
                "state": result.current_state if result else "not_bound",
                "legacy_status": result.legacy_status if result else None,
            },
        }

    def _state(
        self,
        session: Session,
        protocol: ExamProtocol,
        revision: ExamProtocolRevision,
    ) -> str:
        if revision.workflow_state == "correction_open" and revision.submitted_at is None:
            return "correction_open"
        if revision.submitted_at is None:
            return "in_progress"
        participants = self._participant_ids(session, protocol)
        responses = list(
            session.scalars(
                select(ExamProtocolResponse).where(
                    ExamProtocolResponse.exam_protocol_revision_id == revision.id
                )
            )
        )
        if not responses:
            return "awaiting_confirmation"
        if {item.committee_member_id for item in responses} != participants:
            return "reaction_missing"
        return (
            "fully_with_reservation"
            if any(item.response == "reservation" for item in responses)
            else "fully_confirmed"
        )

    def _require_access(
        self,
        session: Session,
        protocol: ExamProtocol,
        scope: AuthorizationScope,
        *,
        edit: bool = False,
        react: bool = False,
        manage: bool = False,
    ) -> tuple[int | None, set[int], bool]:
        actor_id, participants, can_manage = self._access(session, protocol, scope)
        if actor_id not in participants and not can_manage:
            raise PermissionError("Forbidden.")
        if react and actor_id not in participants:
            raise PermissionError("Forbidden.")
        if manage and not can_manage:
            raise PermissionError("Forbidden.")
        if edit and actor_id is None:
            raise PermissionError("Forbidden.")
        return actor_id, participants, can_manage

    def _access(
        self, session: Session, protocol: ExamProtocol, scope: AuthorizationScope
    ) -> tuple[int | None, set[int], bool]:
        slot = session.get(ExamSlot, protocol.exam_slot_id)
        day = session.get(ExamDay, slot.exam_day_id) if slot else None
        exam_round = session.get(ExamRound, day.exam_round_id) if day else None
        committee_id = exam_round.committee_id if exam_round else None
        actor_id = scope.member_for_committee(committee_id)
        return (
            actor_id,
            self._participant_ids(session, protocol),
            scope.can_manage_committee(committee_id),
        )

    @staticmethod
    def _participant_ids(session: Session, protocol: ExamProtocol) -> set[int]:
        return set(
            session.scalars(
                select(ExamProtocolParticipant.committee_member_id).where(
                    ExamProtocolParticipant.exam_protocol_id == protocol.id
                )
            )
        )

    @staticmethod
    def _required_protocol(session: Session, protocol_id: int) -> ExamProtocol:
        protocol = session.get(ExamProtocol, protocol_id)
        if protocol is None:
            raise ValueError("Prüfungsprotokoll nicht gefunden")
        return protocol

    @staticmethod
    def _current_revision(session: Session, protocol: ExamProtocol) -> ExamProtocolRevision:
        revision = session.scalar(
            select(ExamProtocolRevision).where(
                ExamProtocolRevision.exam_protocol_id == protocol.id,
                ExamProtocolRevision.version == protocol.current_version,
            )
        )
        if revision is None:
            raise RuntimeError("Aktueller Protokollstand fehlt")
        return revision

    @staticmethod
    def _entries(session: Session, revision: ExamProtocolRevision) -> list[ExamProtocolEntry]:
        return list(
            session.scalars(
                select(ExamProtocolEntry)
                .where(ExamProtocolEntry.exam_protocol_revision_id == revision.id)
                .order_by(ExamProtocolEntry.id)
            )
        )

    def _revision_content(
        self, session: Session, revision: ExamProtocolRevision
    ) -> tuple[str | None, list[dict[str, str | None]]]:
        return (
            revision.declaration,
            [
                {
                    "category": item.category,
                    "statement": item.statement,
                    "occurred_from": item.occurred_from,
                    "occurred_to": item.occurred_to,
                }
                for item in self._entries(session, revision)
            ],
        )

    def _normalize_content(
        self, payload: dict[str, Any]
    ) -> tuple[str, list[dict[str, str | None]]]:
        declaration = payload.get("declaration")
        if declaration not in DECLARATIONS:
            raise ValueError("Der Prüfungsverlauf muss ausdrücklich festgestellt werden")
        raw_entries = payload.get("entries", [])
        if not isinstance(raw_entries, list):
            raise ValueError("Protokolleinträge müssen als Liste übermittelt werden")
        entries: list[dict[str, str | None]] = []
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

    def _validate_persisted_content(self, session: Session, revision: ExamProtocolRevision) -> None:
        entries = self._entries(session, revision)
        if revision.declaration not in DECLARATIONS:
            raise ValueError("Der Prüfungsverlauf wurde noch nicht festgestellt")
        if revision.declaration == "without_special_occurrences" and entries:
            raise ValueError("Ein regulärer Verlauf enthält keine Besonderheiten")
        if revision.declaration == "with_special_occurrences" and not entries:
            raise ValueError("Ein abweichender Verlauf benötigt mindestens eine Besonderheit")

    @staticmethod
    def _required_version(payload: dict[str, Any]) -> int:
        version = payload.get("version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ValueError("Eine gültige Protokollversion ist erforderlich")
        return version

    @staticmethod
    def _assert_version(revision: ExamProtocolRevision, expected_version: int) -> None:
        if revision.version != expected_version:
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
