"""SQLite engine setup, migration handling, and transaction-scoped sessions."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import MetaData, Table, create_engine, event, inspect, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from .models import Base

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = Path("/data/lzug.sqlite")
BUSY_TIMEOUT_MS = 5_000
SQLITE_JOURNAL_MODE = "wal"
SQLITE_SYNCHRONOUS = 1
REQUIRED_TABLES = frozenset(Base.metadata.tables) | {"schema_migration"}
SCHEMA_PATH = ROOT_DIR / "db" / "schema.sql"
SEED_PATH = ROOT_DIR / "db" / "seed_demo.sql"
MIGRATIONS_PATH = ROOT_DIR / "db" / "migrations"


def database_path(value: str | Path | None = None) -> Path:
    """Resolve a SQLite file path from a CLI value or environment setting.

    ``sqlite:///`` URLs are accepted so deployment environments can expose one
    standard database setting while the application continues to pass a Path
    through its repository and service boundaries.
    """
    if value is None:
        database_url_value = os.environ.get("LZUG_DATABASE_URL")
        database_path_value = os.environ.get("LZUG_DATABASE_PATH")
        if database_url_value and database_path_value:
            raise ValueError("Set only one of LZUG_DATABASE_URL and LZUG_DATABASE_PATH")
        value = database_url_value or database_path_value
    if value is None:
        return DEFAULT_DB_PATH

    raw_value = str(value)
    if not raw_value.startswith("sqlite:"):
        return Path(raw_value).expanduser()

    url = make_url(raw_value)
    if url.drivername not in {"sqlite", "sqlite+pysqlite"}:
        raise ValueError("Only SQLite database URLs are supported")
    if url.query or not url.database or url.database == ":memory:":
        raise ValueError("SQLite database URLs must address a file without query parameters")
    return Path(url.database).expanduser()


def database_url(db_path: Path = DEFAULT_DB_PATH) -> str:
    return f"sqlite:///{Path(db_path)}"


def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        journal_mode = cursor.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        if str(journal_mode).lower() != SQLITE_JOURNAL_MODE:
            raise RuntimeError(f"SQLite WAL mode could not be enabled (got {journal_mode!r})")
        cursor.execute("PRAGMA synchronous = NORMAL")
    finally:
        cursor.close()


def engine_for(db_path: Path = DEFAULT_DB_PATH) -> Engine:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url(db_path), future=True, poolclass=NullPool)
    event.listen(engine, "connect", _configure_sqlite_connection)
    return engine


def connect(db_path: Path = DEFAULT_DB_PATH) -> Connection:
    return engine_for(db_path).connect()


@contextmanager
def session_scope(db_path: Path = DEFAULT_DB_PATH) -> Iterator[Session]:
    """Yield a session that commits on success and rolls back on every error.

    Services and repositories use this context manager as their transaction
    boundary. ``Store`` only flushes, therefore all writes performed during
    the yielded block are committed together or rolled back together.

    Args:
        db_path: SQLite database file used for this unit of work.

    Yields:
        An open SQLAlchemy session.
    """
    engine = engine_for(db_path)
    session_factory = sessionmaker(bind=engine, future=True)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def initialize(
    db_path: Path = DEFAULT_DB_PATH,
    with_seed: bool = False,
    reset: bool = False,
) -> None:
    if reset:
        db_path.unlink(missing_ok=True)
        Path(f"{db_path}-wal").unlink(missing_ok=True)
        Path(f"{db_path}-shm").unlink(missing_ok=True)

    is_new_database = not db_path.exists() or db_path.stat().st_size == 0
    if is_new_database:
        engine = engine_for(db_path)
        raw_connection = engine.raw_connection()
        try:
            raw_connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            if with_seed:
                raw_connection.executescript(SEED_PATH.read_text(encoding="utf-8"))
            raw_connection.commit()
        finally:
            raw_connection.close()
            engine.dispose()

    apply_migrations(db_path)


def apply_migrations(db_path: Path = DEFAULT_DB_PATH) -> None:
    engine = engine_for(db_path)
    raw_connection = engine.raw_connection()
    try:
        bootstrap = MIGRATIONS_PATH / "000_create_schema_migration.sql"
        raw_connection.executescript(bootstrap.read_text(encoding="utf-8"))
        raw_connection.commit()
    finally:
        raw_connection.close()

    migration_table = Table("schema_migration", MetaData(), autoload_with=engine)
    with engine.connect() as connection:
        applied = set(connection.scalars(select(migration_table.c.name)))

    for migration in sorted(MIGRATIONS_PATH.glob("[0-9][0-9][0-9]_*.sql")):
        if migration.name.startswith("000_"):
            continue
        if migration.name in applied:
            continue
        if migration.name == "002_add_person_memberships.sql":
            with engine.connect() as connection:
                has_members = connection.exec_driver_sql(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' "
                    "AND name = 'committee_member'"
                ).first()
            if has_members is None:
                continue
        if migration.name == "003_add_exam_half_years.sql":
            with engine.connect() as connection:
                has_rounds = connection.exec_driver_sql(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' " "AND name = 'exam_round'"
                ).first()
            if has_rounds is None:
                continue
        if migration.name == "004_add_candidate_committee_assignments.sql":
            with engine.connect() as connection:
                has_round_candidates = connection.exec_driver_sql(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' "
                    "AND name = 'round_candidate'"
                ).first()
            if has_round_candidates is None:
                continue
        if migration.name == "005_add_exam_day_attendance.sql":
            with engine.connect() as connection:
                has_slots = connection.exec_driver_sql(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' " "AND name = 'exam_slot'"
                ).first()
            if has_slots is None:
                continue
        raw_connection = engine.raw_connection()
        try:
            raw_connection.executescript(migration.read_text(encoding="utf-8"))
            raw_connection.commit()
        finally:
            raw_connection.close()

    engine.dispose()


def is_available(db_path: Path = DEFAULT_DB_PATH) -> bool:
    try:
        with connect(db_path) as connection:
            connection.execute(select(1))
        return True
    except OSError, RuntimeError, SQLAlchemyError:
        return False


def sqlite_settings(connection: Connection) -> dict[str, str | int]:
    """Return the effective connection settings used by readiness checks."""
    return {
        "foreign_keys": int(connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()),
        "journal_mode": str(connection.exec_driver_sql("PRAGMA journal_mode").scalar_one()).lower(),
        "synchronous": int(connection.exec_driver_sql("PRAGMA synchronous").scalar_one()),
        "busy_timeout": int(connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one()),
    }


def is_ready(db_path: Path = DEFAULT_DB_PATH) -> bool:
    """Check that the database is reachable, initialized, and self-hosting-ready."""
    if not db_path.exists():
        return False
    try:
        with connect(db_path) as connection:
            tables = inspect(connection)
            if not REQUIRED_TABLES.issubset({table for table in tables.get_table_names()}):
                return False
            settings = sqlite_settings(connection)
            return settings == {
                "foreign_keys": 1,
                "journal_mode": SQLITE_JOURNAL_MODE,
                "synchronous": SQLITE_SYNCHRONOUS,
                "busy_timeout": BUSY_TIMEOUT_MS,
            }
    except OSError, RuntimeError, SQLAlchemyError:
        return False
