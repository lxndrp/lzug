"""SQLite composition for the Application-owned exam lifecycle UoW."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.persistence.assessment import SQLiteAssessmentUnitOfWorkFactory
from backend.persistence.calendar_lifecycle import SQLiteCalendarLifecycleWork
from backend.persistence.database import DEFAULT_DB_PATH, session_scope
from backend.persistence.execution import SQLiteExecutionUnitOfWorkFactory
from backend.persistence.identity_lifecycle import SQLiteIdentityLifecycleWork
from backend.persistence.models import ExamDay
from backend.persistence.planning_lifecycle import SQLitePlanningLifecycleWork


class SQLiteExamLifecycleUnitOfWorkFactory:
    """Compose domain-owned ports over one SQLite transaction."""

    def __init__(
        self,
        execution_factory: SQLiteExecutionUnitOfWorkFactory,
        assessment_factory: SQLiteAssessmentUnitOfWorkFactory,
        db_path: Path = DEFAULT_DB_PATH,
        assessment_lifecycle_factory: Callable[[Session], object] | None = None,
    ) -> None:
        self._execution_factory = execution_factory
        self._assessment_factory = assessment_factory
        self._db_path = Path(db_path)
        self._assessment_lifecycle_factory = assessment_lifecycle_factory

    def __call__(self) -> AbstractContextManager[_SQLiteExamLifecycleUnitOfWork]:
        return self._scope()

    def in_session(self, session: Session) -> _SQLiteExamLifecycleUnitOfWork:
        """Compose both domain capabilities over an already owned transaction."""
        return _SQLiteExamLifecycleUnitOfWork(
            self._execution_factory.in_session(session),
            self._assessment_factory.in_session(session),
            session,
            (
                self._assessment_lifecycle_factory(session)
                if self._assessment_lifecycle_factory is not None
                else None
            ),
            SQLitePlanningLifecycleWork(session),
            SQLiteIdentityLifecycleWork(session),
            SQLiteCalendarLifecycleWork(session),
        )

    @contextmanager
    def _scope(self) -> Iterator[_SQLiteExamLifecycleUnitOfWork]:
        with session_scope(self._db_path, begin_immediate=True) as session:
            yield self.in_session(session)


class _SQLiteExamLifecycleUnitOfWork:
    """Provide detached domain capabilities without exposing the SQLAlchemy session."""

    def __init__(
        self,
        execution,
        assessment,
        session: Session,
        assessment_lifecycle,
        planning_lifecycle,
        identity_lifecycle,
        calendar_lifecycle,
    ) -> None:
        self._execution = _SQLiteExamLifecycleExecution(execution, session)
        self._assessment = assessment
        self._assessment_lifecycle = assessment_lifecycle
        self._planning_lifecycle = planning_lifecycle
        self._identity_lifecycle = identity_lifecycle
        self._calendar_lifecycle = calendar_lifecycle

    @property
    def execution(self):
        return self._execution

    @property
    def assessment(self):
        return self._assessment

    @property
    def assessment_lifecycle(self):
        return self._assessment_lifecycle

    @property
    def planning_lifecycle(self):
        return self._planning_lifecycle

    @property
    def identity_lifecycle(self):
        return self._identity_lifecycle

    @property
    def calendar_lifecycle(self):
        return self._calendar_lifecycle


class _SQLiteExamLifecycleExecution:
    """Add explicit lifecycle commands to the ordinary Execution UoW port."""

    def __init__(self, execution, session: Session) -> None:
        self._execution = execution
        self._session = session

    def __getattr__(self, name):
        return getattr(self._execution, name)

    def exam_day_round_id(self, day_id: int) -> int | None:
        day = self._session.get(ExamDay, day_id)
        return day.exam_round_id if day is not None else None

    def exam_day_ids_for_round(self, round_id: int) -> tuple[int, ...]:
        return tuple(
            self._session.scalars(
                select(ExamDay.id).where(ExamDay.exam_round_id == round_id).order_by(ExamDay.id)
            )
        )

    def evaluate_round_decision(self, service, scope, command, decision_type, facts):
        return service.evaluate_decision_intent(self._session, scope, command, decision_type, facts)

    def replay_round_decision(self, service, scope, intent, facts):
        return service.replay_decision_intent(self._session, scope, intent, facts)

    def apply_round_decision(self, service, scope, intent, facts, cancelled_recipients):
        return service.apply_decision_intent(
            self._session, scope, intent, facts, cancelled_recipients
        )

    def evaluate_round_reopen(self, service, scope, command, facts):
        return service.evaluate_reopen_intent(self._session, scope, command, facts)

    def round_reopening_impact(self, service, scope, facts, raw_scope):
        return service.reopening_impact_from_facts(self._session, scope, facts, raw_scope)

    def replay_round_reopen(self, service, scope, intent, facts):
        return service.replay_reopen_intent(self._session, scope, intent, facts)

    def apply_round_reopen(self, service, scope, intent, facts):
        return service.apply_reopen_intent(self._session, scope, intent, facts)

    def evaluate_day_close(self, service, scope, day_id, command, facts):
        return service.evaluate_close_intent(self._session, scope, day_id, command, facts)

    def apply_day_close(self, service, scope, intent, facts):
        return service.apply_close_intent(self._session, scope, intent, facts)

    def day_reopening_impact(self, service, scope, day_id, raw_scope, facts):
        return service.reopening_impact_from_facts(self._session, scope, day_id, raw_scope, facts)

    def evaluate_day_reopen(self, service, scope, day_id, command, facts):
        return service.evaluate_reopen_intent(self._session, scope, day_id, command, facts)

    def begin_day_reopen(self, service, intent):
        return service.begin_reopen_intent(self._session, intent)

    def complete_day_reopen(self, service, scope, handle, facts, assessment_corrections):
        return service.complete_reopen_intent(
            self._session, scope, handle, facts, assessment_corrections
        )

    def replay_day_reopen(self, service, scope, intent, facts):
        return service.replay_reopen_intent(self._session, scope, intent, facts)
