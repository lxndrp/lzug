"""SQLite persistence adapter for the Execution-owned protocol workflow."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.persistence.models import (
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

if TYPE_CHECKING:
    from backend.execution.protocol_ports import (
        ExecutionProtocolSnapshot,
        ProtocolCorrectionOpenWrite,
        ProtocolCorrectionRequestWrite,
        ProtocolDaySnapshot,
        ProtocolEntrySnapshot,
        ProtocolResponseSnapshot,
        ProtocolResponseWrite,
        ProtocolRetentionWrite,
        ProtocolRevisionSnapshot,
        ProtocolRevisionWrite,
        ProtocolSubmissionWrite,
    )


class SQLiteExecutionProtocolStore:
    """Materialize protocol snapshots and persist typed workflow commands."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def protocol_by_id(self, protocol_id: int) -> ExecutionProtocolSnapshot | None:
        protocol = self._session.get(ExamProtocol, protocol_id)
        if protocol is None:
            return None
        slot = self._session.get(ExamSlot, protocol.exam_slot_id)
        day = self._session.get(ExamDay, slot.exam_day_id) if slot is not None else None
        exam_round = self._session.get(ExamRound, day.exam_round_id) if day is not None else None
        participants = list(
            self._session.scalars(
                select(ExamProtocolParticipant.committee_member_id)
                .where(ExamProtocolParticipant.exam_protocol_id == protocol.id)
                .order_by(ExamProtocolParticipant.committee_member_id)
            )
        )
        revisions: list[ProtocolRevisionSnapshot] = []
        for revision in self._session.scalars(
            select(ExamProtocolRevision)
            .where(ExamProtocolRevision.exam_protocol_id == protocol.id)
            .order_by(ExamProtocolRevision.version)
        ):
            entries: list[ProtocolEntrySnapshot] = [
                {
                    "id": entry.id,
                    "category": entry.category,
                    "statement": entry.statement,
                    "occurred_from": entry.occurred_from,
                    "occurred_to": entry.occurred_to,
                    "recorded_by_member_id": entry.recorded_by_member_id,
                    "created_at": entry.created_at,
                }
                for entry in self._session.scalars(
                    select(ExamProtocolEntry)
                    .where(ExamProtocolEntry.exam_protocol_revision_id == revision.id)
                    .order_by(ExamProtocolEntry.id)
                )
            ]
            responses: list[ProtocolResponseSnapshot] = [
                {
                    "id": response.id,
                    "committee_member_id": response.committee_member_id,
                    "response": response.response,
                    "entry_id": response.exam_protocol_entry_id,
                    "statement": response.statement,
                    "responded_at": response.responded_at,
                }
                for response in self._session.scalars(
                    select(ExamProtocolResponse)
                    .where(ExamProtocolResponse.exam_protocol_revision_id == revision.id)
                    .order_by(ExamProtocolResponse.id)
                )
            ]
            revisions.append(
                {
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
                    "entries": entries,
                    "responses": responses,
                }
            )
        revisions_by_id = {item["id"]: item for item in revisions}
        requests = [
            {
                "id": request.id,
                "revision_id": request.exam_protocol_revision_id,
                "version": revisions_by_id[request.exam_protocol_revision_id]["version"],
                "requested_by_member_id": request.requested_by_member_id,
                "reason": request.reason,
                "status": request.status,
                "requested_at": request.requested_at,
                "opened_by_member_id": request.opened_by_member_id,
                "opened_at": request.opened_at,
                "reopening_reference": request.reopening_reference,
            }
            for request in self._session.scalars(
                select(ExamProtocolCorrectionRequest)
                .where(ExamProtocolCorrectionRequest.exam_protocol_id == protocol.id)
                .order_by(ExamProtocolCorrectionRequest.id)
            )
        ]
        retention_row = self._session.scalar(
            select(ExamProtocolRetention).where(
                ExamProtocolRetention.exam_protocol_id == protocol.id
            )
        )
        retention = (
            {
                "rule_reference": retention_row.rule_reference,
                "retain_until": retention_row.retain_until,
                "legal_hold": bool(retention_row.legal_hold),
                "hold_reason": retention_row.hold_reason,
                "updated_by_member_id": retention_row.updated_by_member_id,
                "updated_at": retention_row.updated_at,
            }
            if retention_row is not None
            else None
        )
        reopening_scope: Sequence[str] = ()
        if day is not None and day.closure_status == "reopening":
            reopening = self._session.scalar(
                select(ExamDayReopening).where(
                    ExamDayReopening.exam_day_id == day.id,
                    ExamDayReopening.status == "open",
                )
            )
            if reopening is not None:
                reopening_scope = tuple(json.loads(reopening.scope_json))
        current_revision = next(
            (item for item in revisions if item["version"] == protocol.current_version), None
        )
        late_response_member_ids: Sequence[int] = ()
        if (
            day is not None
            and day.closure_status == "closed_exception"
            and current_revision is not None
        ):
            late_response_member_ids = tuple(
                self._session.scalars(
                    select(ExamDayTask.recipient_member_id)
                    .where(
                        ExamDayTask.exam_day_id == day.id,
                        ExamDayTask.task_type == "protocol_follow_up",
                        ExamDayTask.exam_protocol_revision_id == current_revision["id"],
                        ExamDayTask.status == "open",
                    )
                    .order_by(ExamDayTask.recipient_member_id)
                )
            )
        return cast(
            "ExecutionProtocolSnapshot",
            {
                "id": protocol.id,
                "exam_slot_id": protocol.exam_slot_id,
                "current_version": protocol.current_version,
                "source": protocol.source,
                "created_at": protocol.created_at,
                "updated_at": protocol.updated_at,
                "exam_day_id": day.id if day is not None else None,
                "day_revision": day.revision if day is not None else None,
                "day_status": day.status if day is not None else None,
                "day_closure_status": day.closure_status if day is not None else None,
                "reopening_scope": reopening_scope,
                "committee_id": exam_round.committee_id if exam_round is not None else None,
                "participants": tuple(participants),
                "late_response_member_ids": late_response_member_ids,
                "revisions": tuple(revisions),
                "correction_requests": tuple(requests),
                "retention": retention,
            },
        )

    def protocol_by_slot(self, slot_id: int) -> ExecutionProtocolSnapshot | None:
        protocol_id = self._session.scalar(
            select(ExamProtocol.id).where(ExamProtocol.exam_slot_id == slot_id)
        )
        return self.protocol_by_id(protocol_id) if protocol_id is not None else None

    def protocol_references(self, protocol_id: int) -> dict[str, object]:
        protocol = self._required_protocol(protocol_id)
        slot = self._session.get(ExamSlot, protocol.exam_slot_id)
        day = self._session.get(ExamDay, slot.exam_day_id)
        exam_round = self._session.get(ExamRound, day.exam_round_id)
        round_candidate = self._session.get(RoundCandidate, slot.round_candidate_id)
        candidate = self._session.get(Candidate, round_candidate.candidate_id)
        room = self._session.get(ExamRoom, day.room_id)
        venue = self._session.get(ExamVenue, room.venue_id) if room is not None else None
        candidate_attendance = self._session.scalar(
            select(CandidateExamAttendance).where(CandidateExamAttendance.exam_slot_id == slot.id)
        )
        participant_references = []
        for member_id in self._session.scalars(
            select(ExamProtocolParticipant.committee_member_id)
            .where(ExamProtocolParticipant.exam_protocol_id == protocol.id)
            .order_by(ExamProtocolParticipant.committee_member_id)
        ):
            member = self._session.get(CommitteeMember, member_id)
            person = self._session.get(Person, member.person_id)
            attendance = self._session.scalar(
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
                        "status": attendance.status if attendance is not None else "open",
                        "arrived_at": attendance.arrived_at if attendance is not None else None,
                    },
                }
            )
        result = self._session.scalar(
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
                "status": (
                    candidate_attendance.status if candidate_attendance is not None else "open"
                ),
                "arrived_at": (
                    candidate_attendance.arrived_at if candidate_attendance is not None else None
                ),
            },
            "location": {
                "id": venue.id if venue is not None else None,
                "name": venue.name if venue is not None else "",
                "room": room.name if room is not None else "",
                "city": venue.city if venue is not None else "",
            },
            "participants": participant_references,
            "assessment": {
                "available": result is not None and result.legacy_status is None,
                "exam_result_id": result.id if result is not None else None,
                "state": result.current_state if result is not None else "not_bound",
                "legacy_status": result.legacy_status if result is not None else None,
            },
        }

    def protocol_day_snapshot(self, day_id: int) -> ProtocolDaySnapshot | None:
        day = self._session.get(ExamDay, day_id)
        if day is None:
            return None
        exam_round = self._session.get(ExamRound, day.exam_round_id)
        slots = [
            {
                "exam_slot_id": slot.id,
                "actual_started_at": slot.actual_started_at,
                "execution_status": slot.execution_status,
                "protocol": self.protocol_by_slot(slot.id),
            }
            for slot in self._session.scalars(
                select(ExamSlot).where(ExamSlot.exam_day_id == day_id).order_by(ExamSlot.id)
            )
        ]
        return cast(
            "ProtocolDaySnapshot",
            {
                "exam_day_id": day.id,
                "committee_id": exam_round.committee_id if exam_round is not None else None,
                "slots": tuple(slots),
            },
        )

    def write_protocol_revision(self, command: ProtocolRevisionWrite) -> None:
        protocol = self._required_protocol(command["protocol_id"])
        self._assert_version(protocol, command["expected_version"])
        revision = ExamProtocolRevision(
            exam_protocol_id=protocol.id,
            version=command["expected_version"] + 1,
            declaration=command["declaration"],
            workflow_state=command["workflow_state"],
            previous_revision_id=command["previous_revision_id"],
            correction_request_id=command["correction_request_id"],
            changed_by_member_id=command["actor_member_id"],
            change_reason=command["change_reason"],
            created_at=command["created_at"],
        )
        self._session.add(revision)
        self._session.flush()
        self._session.add_all(
            ExamProtocolEntry(
                exam_protocol_revision_id=revision.id,
                category=entry["category"],
                statement=entry["statement"],
                occurred_from=entry["occurred_from"],
                occurred_to=entry["occurred_to"],
                recorded_by_member_id=command["actor_member_id"],
                created_at=command["created_at"],
            )
            for entry in command["entries"]
        )
        protocol.current_version = revision.version
        protocol.updated_at = command["created_at"]
        self._session.flush()

    def submit_protocol_revision(self, command: ProtocolSubmissionWrite) -> None:
        protocol = self._required_protocol(command["protocol_id"])
        self._assert_version(protocol, command["version"])
        revision = self._current_revision(protocol)
        revision.workflow_state = "submitted"
        revision.submitted_by_member_id = command["actor_member_id"]
        revision.submitted_at = command["submitted_at"]
        protocol.updated_at = command["submitted_at"]
        self._session.flush()

    def write_protocol_response(self, command: ProtocolResponseWrite) -> None:
        protocol = self._required_protocol(command["protocol_id"])
        self._assert_version(protocol, command["version"])
        revision = self._current_revision(protocol)
        self._session.add(
            ExamProtocolResponse(
                exam_protocol_revision_id=revision.id,
                committee_member_id=command["actor_member_id"],
                response=command["response"],
                exam_protocol_entry_id=command["entry_id"],
                statement=command["statement"],
                responded_at=command["responded_at"],
            )
        )
        self._session.flush()

    def write_protocol_correction_request(self, command: ProtocolCorrectionRequestWrite) -> None:
        self._session.add(
            ExamProtocolCorrectionRequest(
                exam_protocol_id=command["protocol_id"],
                exam_protocol_revision_id=command["revision_id"],
                requested_by_member_id=command["actor_member_id"],
                reason=command["reason"],
                status="pending",
                requested_at=command["requested_at"],
            )
        )
        self._session.flush()

    def open_protocol_correction(self, command: ProtocolCorrectionOpenWrite) -> None:
        protocol = self._required_protocol(command["protocol_id"])
        self._assert_version(protocol, command["expected_version"])
        current = self._current_revision(protocol)
        correction_request = self._session.get(
            ExamProtocolCorrectionRequest, command["correction_request_id"]
        )
        if correction_request is None:
            raise RuntimeError("Korrekturanfrage verschwand innerhalb des Execution-UoW")
        revision = ExamProtocolRevision(
            exam_protocol_id=protocol.id,
            version=current.version + 1,
            declaration=current.declaration,
            workflow_state="correction_open",
            previous_revision_id=current.id,
            correction_request_id=correction_request.id,
            changed_by_member_id=command["actor_member_id"],
            change_reason=command["reason"],
            created_at=command["created_at"],
        )
        self._session.add(revision)
        self._session.flush()
        previous_entries = self._session.scalars(
            select(ExamProtocolEntry)
            .where(ExamProtocolEntry.exam_protocol_revision_id == current.id)
            .order_by(ExamProtocolEntry.id)
        )
        self._session.add_all(
            ExamProtocolEntry(
                exam_protocol_revision_id=revision.id,
                category=entry.category,
                statement=entry.statement,
                occurred_from=entry.occurred_from,
                occurred_to=entry.occurred_to,
                recorded_by_member_id=entry.recorded_by_member_id,
                created_at=entry.created_at,
            )
            for entry in previous_entries
        )
        correction_request.status = "opened"
        correction_request.opened_by_member_id = command["actor_member_id"]
        correction_request.opened_at = command["created_at"]
        correction_request.reopening_reference = command["reopening_reference"]
        protocol.current_version = revision.version
        protocol.updated_at = command["created_at"]
        self._session.flush()

    def save_protocol_retention(self, command: ProtocolRetentionWrite) -> None:
        existing = self._session.scalar(
            select(ExamProtocolRetention).where(
                ExamProtocolRetention.exam_protocol_id == command["protocol_id"]
            )
        )
        if existing is None:
            existing = ExamProtocolRetention(exam_protocol_id=command["protocol_id"])
            self._session.add(existing)
        existing.rule_reference = command["rule_reference"]
        existing.retain_until = command["retain_until"]
        existing.legal_hold = int(command["legal_hold"])
        existing.hold_reason = command["hold_reason"]
        existing.updated_by_member_id = command["actor_member_id"]
        existing.updated_at = command["updated_at"]
        self._session.flush()

    def _required_protocol(self, protocol_id: int) -> ExamProtocol:
        protocol = self._session.get(ExamProtocol, protocol_id)
        if protocol is None:
            raise ValueError("Prüfungsprotokoll nicht gefunden")
        return protocol

    def _current_revision(self, protocol: ExamProtocol) -> ExamProtocolRevision:
        revision = self._session.scalar(
            select(ExamProtocolRevision).where(
                ExamProtocolRevision.exam_protocol_id == protocol.id,
                ExamProtocolRevision.version == protocol.current_version,
            )
        )
        if revision is None:
            raise RuntimeError("Aktueller Protokollstand fehlt")
        return revision

    @staticmethod
    def _assert_version(protocol: ExamProtocol, expected_version: int) -> None:
        if protocol.current_version != expected_version:
            raise RuntimeError("Protokollversion änderte sich innerhalb des Execution-UoW")
