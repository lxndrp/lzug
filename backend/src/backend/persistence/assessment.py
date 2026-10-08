"""SQLite persistence boundary for Assessment-owned snapshots and commands."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import OperationalError

from backend.errors import AssessmentWriteConflictError
from backend.persistence.database import DEFAULT_DB_PATH, read_session_scope, session_scope
from backend.persistence.models import (
    AssessmentDisclosure,
    AssessmentModelVersion,
    Candidate,
    Committee,
    CommitteeAssessment,
    CommitteeMember,
    ExamDay,
    ExamDayReopening,
    ExamHalfYear,
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

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _model(row: AssessmentModelVersion) -> dict[str, Any]:
    return {
        "id": row.id,
        "model_key": row.model_key,
        "version": row.version,
        "ihk": row.ihk,
        "occupation": row.occupation,
        "specialization": row.specialization,
        "training_regulation": row.training_regulation,
        "exam_regulation": row.exam_regulation,
        "ihk_guidelines": row.ihk_guidelines,
        "valid_from": row.valid_from,
        "valid_until": row.valid_until,
        "official_scale_min": row.official_scale_min,
        "official_scale_max": row.official_scale_max,
        "rules": json.loads(row.rules_json),
        "retention_rule_reference": row.retention_rule_reference,
        "retention_years": row.retention_years,
        "created_by_member_id": row.created_by_member_id,
        "created_at": row.created_at,
    }


class SQLiteAssessmentUnitOfWorkFactory:
    """Open one session/transaction for Assessment queries and writes."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH, day_mutation_handler=None) -> None:
        self.db_path = Path(db_path)
        self.day_mutation_handler = day_mutation_handler

    def __call__(self, *, write: bool = False) -> AbstractContextManager[Any]:
        return self._scope(write)

    def in_session(self, session: Session) -> SQLiteAssessmentUnitOfWork:
        """Bind Assessment capabilities to an Application-owned session."""
        return SQLiteAssessmentUnitOfWork(session, self.day_mutation_handler)

    @contextmanager
    def _scope(self, write: bool) -> Iterator[Any]:
        scope = (
            session_scope(self.db_path, begin_immediate=True)
            if write
            else read_session_scope(self.db_path)
        )
        try:
            with scope as session:
                yield SQLiteAssessmentUnitOfWork(session, self.day_mutation_handler)
        except OperationalError as error:
            if getattr(error.orig, "sqlite_errorcode", None) == getattr(
                sqlite3, "SQLITE_BUSY_SNAPSHOT", 517
            ):
                raise AssessmentWriteConflictError(
                    "Assessment transaction snapshot is stale"
                ) from error
            raise


class SQLiteAssessmentUnitOfWork:
    def __init__(self, session: Session, day_mutation_handler=None) -> None:
        self._session = session
        self._queries = SQLiteAssessmentQueries(session)
        self._repository = SQLiteAssessmentRepository(session, day_mutation_handler)

    @property
    def queries(self):
        return self._queries

    @property
    def repository(self):
        return self._repository


class SQLiteAssessmentQueries:
    """Materialize Assessment-owned values; no ORM instance crosses this adapter."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_models(self) -> Sequence[dict[str, Any]]:
        return [
            _model(x)
            for x in self.session.scalars(
                select(AssessmentModelVersion).order_by(
                    AssessmentModelVersion.model_key, AssessmentModelVersion.version
                )
            )
        ]

    def model_by_id(self, model_version_id: int) -> dict[str, Any] | None:
        row = self.session.get(AssessmentModelVersion, model_version_id)
        return _model(row) if row else None

    def binding_for_round(self, round_id: int) -> dict[str, Any] | None:
        row = self.session.scalar(
            select(ExamRoundAssessmentBinding).where(
                ExamRoundAssessmentBinding.exam_round_id == round_id
            )
        )
        if row is None:
            return None
        return {
            "id": row.id,
            "round_id": row.exam_round_id,
            "model_version_id": row.assessment_model_version_id,
            "version": row.version,
            "bound_by_member_id": row.bound_by_member_id,
            "binding_reason": row.binding_reason,
            "bound_at": row.bound_at,
        }

    def identity_for_committee(self, committee_id: int) -> dict[str, Any] | None:
        committee = self.session.get(Committee, committee_id)
        if committee is None:
            return None
        members = self.session.scalars(
            select(CommitteeMember)
            .where(CommitteeMember.committee_id == committee_id)
            .order_by(CommitteeMember.id)
        )
        return {
            "committee_id": committee.id,
            "occupation": committee.occupation,
            "ihk": committee.ihk,
            "memberships": [
                {
                    "committee_member_id": m.id,
                    "person_id": m.person_id,
                    "representing_side": m.representing_side,
                    "is_active": bool(m.is_active),
                }
                for m in members
            ],
        }

    def planning_for_round(self, round_id: int) -> dict[str, Any] | None:
        round_ = self.session.get(ExamRound, round_id)
        if round_ is None:
            return None
        half_year = self.session.get(ExamHalfYear, round_.exam_half_year_id)
        if half_year is None:
            return None
        days = list(
            self.session.scalars(
                select(ExamDay)
                .where(ExamDay.exam_round_id == round_id)
                .order_by(ExamDay.date, ExamDay.id)
            )
        )
        effective_date = min(
            (d.date for d in days),
            default=f"{half_year.year:04d}-{'10-01' if half_year.season == 'winter' else '04-01'}",
        )
        candidates = self.session.execute(
            select(RoundCandidate, Candidate)
            .join(Candidate, Candidate.id == RoundCandidate.candidate_id)
            .where(RoundCandidate.exam_round_id == round_id)
            .order_by(RoundCandidate.id)
        ).all()
        return {
            "round_id": round_.id,
            "committee_id": round_.committee_id,
            "half_year": half_year.year,
            "half_year_season": half_year.season,
            "effective_date": effective_date,
            "candidates": [
                {
                    "round_candidate_id": rc.id,
                    "candidate_id": c.id,
                    "specialization": c.specialization,
                    "is_active": bool(rc.is_active),
                }
                for rc, c in candidates
            ],
            "days": self._days(days),
        }

    def protocols_for_round_candidate(self, round_candidate_id: int) -> Sequence[dict[str, Any]]:
        rows = self.session.execute(
            select(ExamProtocol, ExamSlot)
            .join(ExamSlot, ExamSlot.id == ExamProtocol.exam_slot_id)
            .where(ExamSlot.round_candidate_id == round_candidate_id)
            .order_by(ExamProtocol.id)
        ).all()
        return [
            {
                "protocol_id": p.id,
                "slot_id": slot.id,
                "round_candidate_id": round_candidate_id,
                "version": p.current_version,
                "participant_member_ids": sorted(
                    self.session.scalars(
                        select(ExamProtocolParticipant.committee_member_id).where(
                            ExamProtocolParticipant.exam_protocol_id == p.id
                        )
                    )
                ),
            }
            for p, slot in rows
        ]

    def round_has_assessment_inputs(self, round_id: int) -> bool:
        result_ids = (
            select(ExamResult.id)
            .join(RoundCandidate, RoundCandidate.id == ExamResult.round_candidate_id)
            .where(RoundCandidate.exam_round_id == round_id)
        )
        return any(
            self.session.scalar(
                select(func.count()).select_from(cls).where(cls.exam_result_id.in_(result_ids))
            )
            for cls in (
                IndividualAssessment,
                CommitteeAssessment,
                ExternalExamResult,
                ResultCalculation,
                ResultDetermination,
            )
        )

    def days_for_result(self, result_id: int) -> Sequence[dict[str, Any]]:
        return self._days(self._result_days(result_id))

    def day_completion(self, day_id: int) -> dict[str, Any] | None:
        day = self.session.get(ExamDay, day_id)
        if day is None:
            return None
        round_ = self.session.get(ExamRound, day.exam_round_id)
        if round_ is None:
            return None
        slots = self.session.scalars(
            select(ExamSlot).where(ExamSlot.exam_day_id == day_id).order_by(ExamSlot.id)
        )
        rows = []
        for slot in slots:
            result_row = self.session.scalar(
                select(ExamResult).where(ExamResult.round_candidate_id == slot.round_candidate_id)
            )
            if result_row is None:
                result = None
            elif result_row.legacy_status is not None:
                result = {
                    "id": result_row.id,
                    "legacy_status": result_row.legacy_status,
                }
            else:
                binding = self.session.scalar(
                    select(ExamRoundAssessmentBinding).where(
                        ExamRoundAssessmentBinding.exam_round_id == day.exam_round_id
                    )
                )
                if (
                    binding is None
                    or self.session.get(AssessmentModelVersion, binding.assessment_model_version_id)
                    is None
                ):
                    result = {
                        "id": result_row.id,
                        "legacy_status": None,
                        "model": None,
                    }
                else:
                    result = self._result(result_row)
            rows.append(
                {
                    "slot_id": slot.id,
                    "execution_status": slot.execution_status,
                    "result": result,
                }
            )
        return {"day_id": day.id, "committee_id": round_.committee_id, "slots": rows}

    def result_by_id(self, result_id: int) -> dict[str, Any] | None:
        row = self.session.get(ExamResult, result_id)
        return self._result(row) if row else None

    def results_for_round(self, round_id: int) -> Sequence[dict[str, Any]]:
        rows = self.session.scalars(
            select(ExamResult)
            .join(RoundCandidate, RoundCandidate.id == ExamResult.round_candidate_id)
            .where(RoundCandidate.exam_round_id == round_id)
            .order_by(ExamResult.id)
        )
        return [self._result(row) for row in rows]

    def result_for_round_candidate(self, round_candidate_id: int) -> dict[str, Any] | None:
        row = self.session.scalar(
            select(ExamResult).where(ExamResult.round_candidate_id == round_candidate_id)
        )
        return self._result(row) if row else None

    def result_by_slot(self, slot_id: int, day_id: int | None = None) -> dict[str, Any] | None:
        slot = self.session.get(ExamSlot, slot_id)
        if slot is None or (day_id is not None and slot.exam_day_id != day_id):
            return None
        return self.result_for_round_candidate(slot.round_candidate_id)

    def _result_days(self, result_id: int) -> list[ExamDay]:
        return list(
            self.session.scalars(
                select(ExamDay)
                .join(ExamSlot, ExamSlot.exam_day_id == ExamDay.id)
                .join(RoundCandidate, RoundCandidate.id == ExamSlot.round_candidate_id)
                .join(ExamResult, ExamResult.round_candidate_id == RoundCandidate.id)
                .where(ExamResult.id == result_id)
                .distinct()
                .order_by(ExamDay.date, ExamDay.id)
            )
        )

    def _days(self, days: Sequence[ExamDay]) -> list[dict[str, Any]]:
        result = []
        for day in days:
            reopening_ids = []
            if day.closure_status == "reopening":
                for reopening in self.session.scalars(
                    select(ExamDayReopening).where(
                        ExamDayReopening.exam_day_id == day.id, ExamDayReopening.status == "open"
                    )
                ):
                    try:
                        scope = json.loads(reopening.scope_json)
                    except TypeError, json.JSONDecodeError:
                        scope = []
                    reopening_ids.extend(
                        int(x.split(":", 1)[1])
                        for x in scope
                        if isinstance(x, str)
                        and x.startswith("exam_result:")
                        and x.split(":", 1)[1].isdigit()
                    )
            result.append(
                {
                    "day_id": day.id,
                    "date": day.date,
                    "revision": day.revision,
                    "status": day.status,
                    "closure_status": day.closure_status,
                    "reopening_assessment_result_ids": sorted(set(reopening_ids)),
                }
            )
        return result

    def _result(self, row: ExamResult) -> dict[str, Any]:
        rc = self.session.get(RoundCandidate, row.round_candidate_id)
        if rc is None:
            raise ValueError("Assessment result references a missing round candidate")
        round_ = self.session.get(ExamRound, rc.exam_round_id)
        candidate = self.session.get(Candidate, rc.candidate_id)
        binding = self.session.scalar(
            select(ExamRoundAssessmentBinding).where(
                ExamRoundAssessmentBinding.exam_round_id == rc.exam_round_id
            )
        )
        if round_ is None or candidate is None or binding is None:
            raise ValueError("Assessment result has no complete round, candidate, or model binding")
        model_row = self.session.get(AssessmentModelVersion, binding.assessment_model_version_id)
        if model_row is None:
            raise ValueError("Assessment binding references a missing model")
        result_id = row.id

        def rows(cls, order):
            return list(
                self.session.scalars(
                    select(cls).where(cls.exam_result_id == result_id).order_by(*order)
                )
            )

        individuals = rows(
            IndividualAssessment,
            (
                IndividualAssessment.component_key,
                IndividualAssessment.criterion_key,
                IndividualAssessment.assessor_member_id,
                IndividualAssessment.revision,
            ),
        )
        components = rows(
            CommitteeAssessment, (CommitteeAssessment.component_key, CommitteeAssessment.revision)
        )
        external = rows(
            ExternalExamResult, (ExternalExamResult.area_key, ExternalExamResult.revision)
        )
        calculations = rows(ResultCalculation, (ResultCalculation.version,))
        determinations = rows(ResultDetermination, (ResultDetermination.revision,))
        corrections = rows(ResultCorrection, (ResultCorrection.id,))
        communications = rows(ResultCommunication, (ResultCommunication.id,))
        retention = self.session.scalar(
            select(ResultRetention).where(ResultRetention.exam_result_id == result_id)
        )
        exports = rows(ResultExport, (ResultExport.id,))
        disclosures = rows(AssessmentDisclosure, (AssessmentDisclosure.component_key,))
        confirmations = list(
            self.session.scalars(
                select(ResultRecordConfirmation)
                .join(
                    ResultDetermination,
                    ResultDetermination.id == ResultRecordConfirmation.result_determination_id,
                )
                .where(ResultDetermination.exam_result_id == result_id)
                .order_by(ResultRecordConfirmation.id)
            )
        )
        confirmation_by_det: dict[int, list[int]] = {}
        for x in confirmations:
            confirmation_by_det.setdefault(x.result_determination_id, []).append(
                x.committee_member_id
            )
        return {
            "id": row.id,
            "round_id": round_.id,
            "committee_id": round_.committee_id,
            "round_candidate_id": row.round_candidate_id,
            "version": row.version,
            "state": row.current_state,
            "correction_open": bool(row.correction_open),
            "legacy_status": row.legacy_status,
            "subject": {
                "candidate_id": candidate.id,
                "first_name": candidate.first_name,
                "last_name": candidate.last_name,
                "ihk_exam_number": candidate.ihk_exam_number,
                "specialization": candidate.specialization,
            },
            "model": _model(model_row),
            "binding": {
                "id": binding.id,
                "round_id": round_.id,
                "model_version_id": binding.assessment_model_version_id,
                "version": binding.version,
                "bound_by_member_id": binding.bound_by_member_id,
                "binding_reason": binding.binding_reason,
                "bound_at": binding.bound_at,
            },
            "participant_member_ids": sorted(
                {
                    member_id
                    for protocol in self.protocols_for_round_candidate(row.round_candidate_id)
                    for member_id in protocol["participant_member_ids"]
                }
            ),
            "days": self._days(self._result_days(result_id)),
            "individual_assessments": [
                {
                    "id": x.id,
                    "component_key": x.component_key,
                    "criterion_key": x.criterion_key,
                    "assessor_member_id": x.assessor_member_id,
                    "revision": x.revision,
                    "raw_points": x.raw_points,
                    "normalized_points": x.normalized_points,
                    "rationale": x.rationale,
                    "status": x.status,
                    "previous_assessment_id": x.previous_assessment_id,
                    "change_reason": x.change_reason,
                    "submitted_at": x.submitted_at,
                    "created_at": x.created_at,
                }
                for x in individuals
            ],
            "component_assessments": [
                {
                    "id": x.id,
                    "component_key": x.component_key,
                    "revision": x.revision,
                    "points": x.points,
                    "rationale": x.rationale,
                    "participant_member_ids": json.loads(x.participant_member_ids_json),
                    "vote": json.loads(x.vote_json),
                    "dissent": json.loads(x.dissent_json),
                    "status": x.status,
                    "previous_assessment_id": x.previous_assessment_id,
                    "determined_by_member_id": x.determined_by_member_id,
                    "determined_at": x.determined_at,
                }
                for x in components
            ],
            "external_results": [
                {
                    "id": x.id,
                    "area_key": x.area_key,
                    "revision": x.revision,
                    "points": x.points,
                    "grade": x.grade,
                    "professional_status": x.professional_status,
                    "determining_authority": x.determining_authority,
                    "source_reference": x.source_reference,
                    "status": x.status,
                    "recorded_by_member_id": x.recorded_by_member_id,
                    "recorded_at": x.recorded_at,
                    "previous_external_result_id": x.previous_external_result_id,
                    "correction_reason": x.correction_reason,
                    "confirmed_by_member_id": x.confirmed_by_member_id,
                    "confirmed_at": x.confirmed_at,
                }
                for x in external
            ],
            "disclosures": [
                {
                    "component_key": x.component_key,
                    "disclosed_by_member_id": x.disclosed_by_member_id,
                    "disclosed_at": x.disclosed_at,
                }
                for x in disclosures
            ],
            "calculations": [
                {
                    "id": x.id,
                    "version": x.version,
                    "total_points": x.total_points,
                    "grade": x.grade,
                    "passed": bool(x.passed),
                    "path": json.loads(x.calculation_path_json),
                    "input_fingerprint": x.input_fingerprint,
                    "created_at": x.created_at,
                }
                for x in calculations
            ],
            "determinations": [
                {
                    "id": x.id,
                    "revision": x.revision,
                    "calculation_id": x.result_calculation_id,
                    "participant_member_ids": json.loads(x.participant_member_ids_json),
                    "vote": json.loads(x.vote_json),
                    "dissent": json.loads(x.dissent_json),
                    "status": x.status,
                    "previous_determination_id": x.previous_determination_id,
                    "correction_id": x.correction_id,
                    "determined_by_member_id": x.determined_by_member_id,
                    "determined_at": x.determined_at,
                }
                for x in determinations
            ],
            "record_confirmations": [
                {
                    "id": x.id,
                    "determination_id": x.result_determination_id,
                    "committee_member_id": x.committee_member_id,
                    "confirmed_at": x.confirmed_at,
                }
                for x in confirmations
            ],
            "corrections": [
                {
                    "id": x.id,
                    "determination_id": x.result_determination_id,
                    "reason": x.reason,
                    "requested_by_member_id": x.requested_by_member_id,
                    "status": x.status,
                    "reopening_reference": x.reopening_reference,
                    "requested_at": x.requested_at,
                    "completed_at": x.completed_at,
                }
                for x in corrections
            ],
            "communications": [
                {
                    "id": x.id,
                    "determination_id": x.result_determination_id,
                    "method": x.method,
                    "responsible_member_id": x.responsible_member_id,
                    "communicated_at": x.communicated_at,
                    "external_document_status": x.external_document_status,
                    "external_document_reference": x.external_document_reference,
                    "status": x.status,
                    "created_at": x.created_at,
                }
                for x in communications
            ],
            "retention": (
                {
                    "version": row.version,
                    "rule_reference": retention.rule_reference,
                    "period_start": retention.period_start,
                    "retain_until": retention.retain_until,
                    "legal_hold": bool(retention.legal_hold),
                    "hold_reason": retention.hold_reason,
                    "updated_by_member_id": retention.updated_by_member_id,
                    "updated_at": retention.updated_at,
                }
                if retention
                else None
            ),
            "exports": [
                {
                    "id": x.id,
                    "determination_id": x.result_determination_id,
                    "export_kind": x.export_kind,
                    "status": x.status,
                    "generated_by_member_id": x.generated_by_member_id,
                    "generated_at": x.generated_at,
                }
                for x in exports
            ],
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }


class SQLiteAssessmentRepository:
    """Persist commands atomically; every result write claims its aggregate version first."""

    def __init__(self, session: Session, day_mutation_handler=None) -> None:
        self.session = session
        self.day_mutation_handler = day_mutation_handler

    def _claim(self, result_id: int, expected: int, *, state: str | None = None) -> ExamResult:
        values: dict[str, Any] = {"version": ExamResult.version + 1}
        if state is not None:
            values["current_state"] = state
        values["updated_at"] = func.strftime("%Y-%m-%dT%H:%M:%SZ", "now")
        changed = self.session.execute(
            update(ExamResult)
            .where(ExamResult.id == result_id, ExamResult.version == expected)
            .values(**values)
        )
        if changed.rowcount != 1:
            raise AssessmentWriteConflictError("Assessment result version conflict")
        row = self.session.get(ExamResult, result_id)
        if row is None:
            raise ValueError("Assessment result not found")
        return row

    def create_model(self, command: dict[str, Any]) -> dict[str, Any]:
        row = AssessmentModelVersion(
            model_key=command["model_key"],
            version=command["version"],
            ihk=command["ihk"],
            occupation=command["occupation"],
            specialization=command["specialization"],
            training_regulation=command["training_regulation"],
            exam_regulation=command["exam_regulation"],
            ihk_guidelines=command["ihk_guidelines"],
            valid_from=command["valid_from"],
            valid_until=command["valid_until"],
            official_scale_min=command["official_scale_min"],
            official_scale_max=command["official_scale_max"],
            rules_json=_json(command["rules"]),
            retention_rule_reference=command["retention_rule_reference"],
            retention_years=command["retention_years"],
            created_by_member_id=command["actor_member_id"],
            created_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
        )
        self.session.add(row)
        self.session.flush()
        return _model(row)

    def bind_round(self, command: dict[str, Any]) -> dict[str, Any] | None:
        row = self.session.scalar(
            select(ExamRoundAssessmentBinding).where(
                ExamRoundAssessmentBinding.exam_round_id == command["round_id"]
            )
        )
        if row is None:
            if command["expected_binding_version"] is not None:
                raise AssessmentWriteConflictError("Assessment binding version conflict")
            row = ExamRoundAssessmentBinding(
                exam_round_id=command["round_id"],
                assessment_model_version_id=command["model_version_id"],
                version=1,
                bound_by_member_id=command["actor_member_id"],
                binding_reason=command["reason"],
                bound_at=command["bound_at"],
            )
            self.session.add(row)
        else:
            if row.version != command["expected_binding_version"]:
                raise AssessmentWriteConflictError("Assessment binding version conflict")
            expected = command["expected_binding_version"]
            changed = self.session.execute(
                update(ExamRoundAssessmentBinding)
                .where(
                    ExamRoundAssessmentBinding.id == row.id,
                    ExamRoundAssessmentBinding.version == expected,
                )
                .values(
                    assessment_model_version_id=command["model_version_id"],
                    version=expected + 1,
                    bound_by_member_id=command["actor_member_id"],
                    binding_reason=command["reason"],
                    bound_at=command["bound_at"],
                )
            )
            if changed.rowcount != 1:
                raise AssessmentWriteConflictError("Assessment binding version conflict")
            self.session.expire(row)
            row = self.session.get(ExamRoundAssessmentBinding, row.id)
            assert row is not None
        self.session.flush()
        return {
            "id": row.id,
            "round_id": row.exam_round_id,
            "model_version_id": row.assessment_model_version_id,
            "version": row.version,
            "bound_by_member_id": row.bound_by_member_id,
            "binding_reason": row.binding_reason,
            "bound_at": row.bound_at,
        }

    def ensure_round_results(self, command: dict[str, Any]) -> None:
        binding = self.session.scalar(
            select(ExamRoundAssessmentBinding).where(
                ExamRoundAssessmentBinding.exam_round_id == command["round_id"]
            )
        )
        if binding is None or binding.version != command["expected_binding_version"]:
            raise AssessmentWriteConflictError("Assessment binding version conflict")
        candidates = list(
            self.session.scalars(
                select(RoundCandidate).where(
                    RoundCandidate.exam_round_id == command["round_id"],
                    RoundCandidate.is_active == 1,
                )
            )
        )
        existing = set(
            self.session.scalars(
                select(ExamResult.round_candidate_id).where(
                    ExamResult.round_candidate_id.in_([x.id for x in candidates])
                )
            )
        )
        for candidate in candidates:
            if candidate.id not in existing:
                self.session.add(
                    ExamResult(
                        round_candidate_id=candidate.id,
                        current_state="incomplete",
                        correction_open=0,
                        version=1,
                        source="application",
                    )
                )
        self.session.flush()

    def save_individual_assessment(self, c: dict[str, Any]) -> None:
        row = self._claim(c["result_id"], c["expected_result_version"])
        current = self.session.scalar(
            select(IndividualAssessment)
            .where(
                IndividualAssessment.exam_result_id == row.id,
                IndividualAssessment.component_key == c["component_key"],
                IndividualAssessment.criterion_key == c["criterion_key"],
                IndividualAssessment.assessor_member_id == c["assessor_member_id"],
                IndividualAssessment.status.in_(["draft", "submitted", "withdrawn"]),
            )
            .order_by(IndividualAssessment.revision.desc())
        )
        if current:
            current.status = "superseded"
        self.session.add(
            IndividualAssessment(
                exam_result_id=row.id,
                component_key=c["component_key"],
                criterion_key=c["criterion_key"],
                assessor_member_id=c["assessor_member_id"],
                revision=(current.revision + 1 if current else 1),
                raw_points=c["raw_points"],
                normalized_points=c["normalized_points"],
                rationale=c["rationale"],
                status=c["status"],
                previous_assessment_id=c["previous_assessment_id"],
                change_reason=c["change_reason"],
                submitted_at=c["submitted_at"],
                created_at=c["created_at"],
            )
        )
        self.session.flush()

    def save_calculation(self, c: dict[str, Any]) -> None:
        row = self._claim(c["result_id"], c["expected_result_version"], state=c["result_state"])
        if self.session.scalar(
            select(ResultCalculation.id).where(
                ResultCalculation.exam_result_id == row.id,
                ResultCalculation.input_fingerprint == c["input_fingerprint"],
            )
        ):
            return
        self.session.add(
            ResultCalculation(
                exam_result_id=row.id,
                version=c["version"],
                input_fingerprint=c["input_fingerprint"],
                total_points=c["total_points"],
                grade=c["grade"],
                passed=int(c["passed"]),
                calculation_path_json=_json(c["path"]),
                created_at=c["created_at"],
            )
        )
        self.session.flush()

    def set_result_state(self, c: dict[str, Any]) -> None:
        changed = self.session.execute(
            update(ExamResult)
            .where(
                ExamResult.id == c["result_id"],
                ExamResult.version == c["expected_result_version"],
            )
            .values(current_state=c["state"])
        )
        if changed.rowcount != 1:
            raise AssessmentWriteConflictError("Assessment result version conflict")

    def disclose_component(self, c: dict[str, Any]) -> None:
        self._claim(c["result_id"], c["expected_result_version"])
        self.session.add(
            AssessmentDisclosure(
                exam_result_id=c["result_id"],
                component_key=c["component_key"],
                disclosed_by_member_id=c["disclosed_by_member_id"],
                disclosed_at=c["disclosed_at"],
            )
        )
        self.session.flush()

    def determine_component(self, c: dict[str, Any]) -> None:
        row = self._claim(c["result_id"], c["expected_result_version"])
        old = self.session.scalar(
            select(CommitteeAssessment).where(
                CommitteeAssessment.exam_result_id == row.id,
                CommitteeAssessment.component_key == c["component_key"],
                CommitteeAssessment.status == "current",
            )
        )
        if old:
            old.status = "superseded"
        self.session.add(
            CommitteeAssessment(
                exam_result_id=row.id,
                component_key=c["component_key"],
                revision=c["revision"],
                points=c["points"],
                rationale=c["rationale"],
                participant_member_ids_json=_json(sorted(c["participant_member_ids"])),
                vote_json=_json(c["vote"]),
                dissent_json=_json(c["dissent"]),
                status="current",
                previous_assessment_id=c["previous_assessment_id"],
                determined_by_member_id=c["determined_by_member_id"],
                determined_at=c["determined_at"],
            )
        )
        self.session.flush()

    def record_external_result(self, c: dict[str, Any]) -> None:
        row = self._claim(c["result_id"], c["expected_result_version"], state=c["result_state"])
        old = self.session.scalar(
            select(ExternalExamResult)
            .where(
                ExternalExamResult.exam_result_id == row.id,
                ExternalExamResult.area_key == c["area_key"],
            )
            .order_by(ExternalExamResult.revision.desc())
        )
        if old:
            old.status = "replaced"
        self.session.add(
            ExternalExamResult(
                exam_result_id=row.id,
                area_key=c["area_key"],
                revision=c["revision"],
                points=c["points"],
                grade=c["grade"],
                professional_status=c["professional_status"],
                determining_authority=c["determining_authority"],
                source_reference=c["source_reference"],
                status="unconfirmed",
                recorded_by_member_id=c["recorded_by_member_id"],
                recorded_at=c["recorded_at"],
                previous_external_result_id=c["previous_external_result_id"],
                correction_reason=c["correction_reason"],
            )
        )
        self.session.flush()

    def confirm_external_result(self, c: dict[str, Any]) -> None:
        row = self._claim(c["result_id"], c["expected_result_version"])
        ext = self.session.get(ExternalExamResult, c["external_result_id"])
        if ext is None or ext.exam_result_id != row.id or ext.status != "unconfirmed":
            raise ValueError("External result is not confirmable")
        ext.status = "confirmed"
        ext.confirmed_by_member_id = c["confirmed_by_member_id"]
        ext.confirmed_at = c["confirmed_at"]
        self.session.flush()

    def determine_result(self, c: dict[str, Any]) -> None:
        row = self._claim(c["result_id"], c["expected_result_version"], state="determined")
        old = self.session.scalar(
            select(ResultDetermination).where(
                ResultDetermination.exam_result_id == row.id,
                ResultDetermination.status == "current",
            )
        )
        if old:
            old.status = "superseded"
            for communication in self.session.scalars(
                select(ResultCommunication).where(
                    ResultCommunication.result_determination_id == old.id,
                    ResultCommunication.status == "current",
                )
            ):
                communication.status = "obsolete"
            for export in self.session.scalars(
                select(ResultExport).where(
                    ResultExport.result_determination_id == old.id,
                    ResultExport.status == "determined",
                )
            ):
                export.status = "superseded"
        self.session.add(
            ResultDetermination(
                exam_result_id=row.id,
                revision=c["revision"],
                result_calculation_id=c["calculation_id"],
                participant_member_ids_json=_json(sorted(c["participant_member_ids"])),
                vote_json=_json(c["vote"]),
                dissent_json=_json(c["dissent"]),
                status="current",
                previous_determination_id=c["previous_determination_id"],
                correction_id=c["correction_id"],
                determined_by_member_id=c["determined_by_member_id"],
                determined_at=c["determined_at"],
            )
        )
        if c["correction_id"] is not None:
            corr = self.session.get(ResultCorrection, c["correction_id"])
            if corr:
                corr.status = "completed"
                corr.completed_at = c["determined_at"]
        row.correction_open = 0
        self.session.flush()

    def confirm_record(self, c: dict[str, Any]) -> None:
        self._claim(c["result_id"], c["expected_result_version"])
        self.session.add(
            ResultRecordConfirmation(
                result_determination_id=c["determination_id"],
                committee_member_id=c["committee_member_id"],
                confirmed_at=c["confirmed_at"],
            )
        )
        self.session.flush()

    def open_correction(self, c: dict[str, Any]) -> None:
        row = self._claim(c["result_id"], c["expected_result_version"])
        self.session.add(
            ResultCorrection(
                exam_result_id=row.id,
                result_determination_id=c["determination_id"],
                reason=c["reason"],
                requested_by_member_id=c["requested_by_member_id"],
                status="open",
                reopening_reference=c["reopening_reference"],
                requested_at=c["requested_at"],
            )
        )
        row.correction_open = 1
        self.session.flush()

    def open_day_reopening_correction(self, c: dict[str, Any]) -> dict[str, Any]:
        """Claim the result revision and open its correction inside the caller's UoW."""
        result = self.session.get(ExamResult, c["result_id"])
        if result is None:
            raise ValueError("Assessment result not found")
        determination = self.session.scalar(
            select(ResultDetermination).where(
                ResultDetermination.exam_result_id == result.id,
                ResultDetermination.status == "current",
            )
        )
        if determination is None:
            return {
                "result_id": result.id,
                "result_version": result.version,
                "determination_id": None,
                "participant_member_ids": [],
                "communicated": False,
                "ihk_processed": False,
            }

        result = self._claim(result.id, c["expected_result_version"])
        correction = self.session.scalar(
            select(ResultCorrection).where(
                ResultCorrection.exam_result_id == result.id,
                ResultCorrection.status == "open",
            )
        )
        if correction is None:
            self.session.add(
                ResultCorrection(
                    exam_result_id=result.id,
                    result_determination_id=determination.id,
                    reason=c["reason"],
                    requested_by_member_id=c["requested_by_member_id"],
                    status="open",
                    reopening_reference=c["reopening_reference"],
                    requested_at=c["requested_at"],
                )
            )
        result.correction_open = 1
        communications = list(
            self.session.scalars(
                select(ResultCommunication).where(
                    ResultCommunication.exam_result_id == result.id,
                    ResultCommunication.status == "current",
                )
            )
        )
        self.session.flush()
        return {
            "result_id": result.id,
            "result_version": result.version,
            "determination_id": determination.id,
            "participant_member_ids": json.loads(determination.participant_member_ids_json),
            "communicated": bool(communications),
            "ihk_processed": any(item.external_document_status for item in communications),
        }

    def communicate_result(self, c: dict[str, Any]) -> None:
        row = self._claim(c["result_id"], c["expected_result_version"], state="communicated")
        for old in self.session.scalars(
            select(ResultCommunication).where(
                ResultCommunication.exam_result_id == row.id,
                ResultCommunication.status == "current",
            )
        ):
            old.status = "obsolete"
        self.session.add(
            ResultCommunication(
                exam_result_id=row.id,
                result_determination_id=c["determination_id"],
                method=c["method"],
                responsible_member_id=c["responsible_member_id"],
                communicated_at=c["communicated_at"],
                external_document_status=c["external_document_status"],
                external_document_reference=c["external_document_reference"],
                status="current",
                created_at=c["created_at"],
            )
        )
        self.session.flush()

    def save_retention(self, c: dict[str, Any]) -> None:
        row = self._claim(c["result_id"], c["expected_result_version"])
        existing = self.session.scalar(
            select(ResultRetention).where(ResultRetention.exam_result_id == row.id)
        )
        if existing is None:
            existing = ResultRetention(exam_result_id=row.id, rule_reference=c["rule_reference"])
            self.session.add(existing)
        existing.rule_reference = c["rule_reference"]
        existing.period_start = c["period_start"]
        existing.retain_until = c["retain_until"]
        existing.legal_hold = int(c["legal_hold"])
        existing.hold_reason = c["hold_reason"]
        existing.updated_by_member_id = c["updated_by_member_id"]
        existing.updated_at = c["updated_at"]
        self.session.flush()

    def record_export(self, c: dict[str, Any]) -> dict[str, Any]:
        checked = self.session.execute(
            update(ExamResult)
            .where(
                ExamResult.id == c["result_id"],
                ExamResult.version == c["expected_result_version"],
            )
            .values(version=ExamResult.version)
        )
        if checked.rowcount != 1:
            raise AssessmentWriteConflictError("Assessment result version conflict")
        row = ResultExport(
            exam_result_id=c["result_id"],
            result_determination_id=c["determination_id"],
            export_kind=c["export_kind"],
            status=c["status"],
            generated_by_member_id=c["generated_by_member_id"],
            generated_at=c["generated_at"],
        )
        self.session.add(row)
        self.session.flush()
        return {
            "id": row.id,
            "determination_id": row.result_determination_id,
            "export_kind": row.export_kind,
            "status": row.status,
            "generated_by_member_id": row.generated_by_member_id,
            "generated_at": row.generated_at,
        }

    def complete_result_day_mutation(
        self,
        result_id: int,
        kind: str,
        payload: Mapping[str, Any],
        actor_member_id: int,
        reason: str | None = None,
    ) -> None:
        if self.day_mutation_handler is not None:
            self.day_mutation_handler(
                self.session,
                result_id,
                kind,
                dict(payload),
                actor_member_id,
                reason,
            )
