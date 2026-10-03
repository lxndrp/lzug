"""Concrete application wiring for the canonical backend runtime."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from backend.identity.admin_service import OperatorAuthService
from backend.identity.auth import AuthenticationRepository
from backend.identity.authorization import AuthorizationService
from backend.identity.committee_admin import CommitteeAdminService
from backend.identity.local_auth import LocalAuthService
from backend.identity.people import IdentityService
from backend.integrations.holiday_provider import PythonHolidaysProvider
from backend.persistence.auth import (
    SQLiteAuthenticationRepository,
    SQLiteOperatorAuthUnitOfWorkFactory,
)
from backend.persistence.candidate_days import SQLiteCandidateDayUnitOfWorkFactory
from backend.persistence.committee_admin import SQLiteCommitteeAdminUnitOfWorkFactory
from backend.persistence.identity import (
    SQLiteIdentityQueryFactory,
    SQLiteIdentityUnitOfWorkFactory,
)
from backend.persistence.local_auth import (
    SQLiteLocalAuthenticationKey,
    SQLiteLocalAuthUnitOfWorkFactory,
)
from backend.planning.candidate_days import CandidateDayService
from backend.settings import RuntimeSettings


def candidate_day_service(db_path: Path) -> CandidateDayService:
    """Wire the planning port to SQLite and the configured holiday adapter."""
    return CandidateDayService(
        SQLiteCandidateDayUnitOfWorkFactory(db_path),
        PythonHolidaysProvider(),
    )


def authentication_repository(db_path: Path) -> AuthenticationRepository:
    """Wire Identity account and session operations to the SQLite adapter."""
    return SQLiteAuthenticationRepository(db_path)


def operator_auth_service(db_path: Path) -> OperatorAuthService:
    """Wire operator authentication commands to the SQLite identity UoW."""
    return OperatorAuthService(SQLiteOperatorAuthUnitOfWorkFactory(db_path))


def local_auth_service(
    db_path: Path,
    *,
    session_ttl: timedelta,
    settings: RuntimeSettings | None,
    authentication: AuthenticationRepository | None = None,
) -> LocalAuthService:
    """Wire local Identity auth ports to SQLite and the instance key store."""
    selected_authentication = authentication or SQLiteAuthenticationRepository(db_path)
    return LocalAuthService(
        unit_of_work_factory=SQLiteLocalAuthUnitOfWorkFactory(
            db_path, authentication=selected_authentication
        ),
        key_provider=SQLiteLocalAuthenticationKey(
            db_path, settings=settings.local_auth if settings else None
        ),
        session_ttl=session_ttl,
    )


def identity_service(db_path: Path) -> IdentityService:
    """Wire Identity's write/read ports to their SQLite adapters."""
    return IdentityService(
        SQLiteIdentityUnitOfWorkFactory(db_path),
        SQLiteIdentityQueryFactory(db_path),
    )


def authorization_service(db_path: Path) -> AuthorizationService:
    """Wire actor resolution to Identity's active-membership query port."""
    return AuthorizationService(identity_service(db_path))


def committee_admin_service(db_path: Path) -> CommitteeAdminService:
    """Wire Identity committee commands to their transactional SQLite adapter."""
    return CommitteeAdminService(SQLiteCommitteeAdminUnitOfWorkFactory(db_path))
