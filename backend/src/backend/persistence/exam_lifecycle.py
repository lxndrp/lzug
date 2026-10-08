"""SQLite composition for the Application-owned exam lifecycle UoW."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path

from sqlalchemy.orm import Session

from backend.persistence.assessment import SQLiteAssessmentUnitOfWorkFactory
from backend.persistence.calendar_lifecycle import SQLiteCalendarLifecycleWork
from backend.persistence.database import DEFAULT_DB_PATH, session_scope
from backend.persistence.execution import SQLiteExecutionUnitOfWorkFactory
from backend.persistence.identity_lifecycle import SQLiteIdentityLifecycleWork
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

    def close_exam_day(
        self,
        service,
        assessment_lifecycle,
        planning_lifecycle,
        identity_lifecycle,
        scope,
        day_id: int,
        payload: dict,
    ):
        """Run the Execution-owned close rule inside this composed UoW."""
        return service.close_in_transaction(
            self._session,
            scope,
            day_id,
            payload,
            assessment_lifecycle,
            planning_lifecycle,
            identity_lifecycle,
        )

    def reopen_exam_day(
        self,
        service,
        assessment_lifecycle,
        planning_lifecycle,
        identity_lifecycle,
        scope,
        day_id: int,
        payload: dict,
    ):
        """Run the Execution-owned reopening rule inside this composed UoW."""
        return service.reopen_in_transaction(
            self._session,
            scope,
            day_id,
            payload,
            assessment_lifecycle,
            planning_lifecycle,
            identity_lifecycle,
        )

    def close_exam_round(
        self,
        service,
        assessment_lifecycle,
        planning_lifecycle,
        identity_lifecycle,
        calendar_lifecycle,
        scope,
        round_id: int,
        payload: dict,
    ):
        """Run the Execution-owned close rule inside this composed UoW."""
        return service.decide_in_transaction(
            self._session,
            scope,
            round_id,
            payload,
            "close",
            assessment_lifecycle,
            planning_lifecycle,
            identity_lifecycle,
            calendar_lifecycle,
        )

    def cancel_exam_round(
        self,
        service,
        assessment_lifecycle,
        planning_lifecycle,
        identity_lifecycle,
        calendar_lifecycle,
        scope,
        round_id: int,
        payload: dict,
    ):
        """Run the Execution-owned cancellation rule inside this composed UoW."""
        return service.decide_in_transaction(
            self._session,
            scope,
            round_id,
            payload,
            "cancel",
            assessment_lifecycle,
            planning_lifecycle,
            identity_lifecycle,
            calendar_lifecycle,
        )

    def reopen_exam_round(
        self,
        service,
        assessment_lifecycle,
        planning_lifecycle,
        identity_lifecycle,
        calendar_lifecycle,
        scope,
        round_id: int,
        payload: dict,
    ):
        """Run the Execution-owned round reopening rule inside this composed UoW."""
        return service.reopen_in_transaction(
            self._session,
            scope,
            round_id,
            payload,
            assessment_lifecycle,
            planning_lifecycle,
            identity_lifecycle,
        )
