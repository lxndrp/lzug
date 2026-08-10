"""SQLite engine setup, migration handling, and transaction-scoped sessions."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import MetaData, Table, create_engine, event, inspect, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from .models import Base

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = Path("/data")
DEFAULT_DB_PATH = Path("/data/lzug.sqlite")
DEFAULT_DOCUMENTS_PATH = Path("/data/documents")
DEFAULT_BACKUPS_PATH = Path("/data/backups")
DEFAULT_MIN_FREE_BYTES = 64 * 1024 * 1024
BUSY_TIMEOUT_MS = 5_000
SQLITE_JOURNAL_MODE = "wal"
SQLITE_SYNCHRONOUS = 1
REQUIRED_TABLES = frozenset(Base.metadata.tables) | {"schema_migration"}
SCHEMA_PATH = ROOT_DIR / "db" / "schema.sql"
SEED_PATH = ROOT_DIR / "db" / "seed_demo.sql"
MIGRATIONS_PATH = ROOT_DIR / "db" / "migrations"


class PersistenceConfigurationError(RuntimeError):
    """Raised when persistent storage cannot serve the runtime."""


@dataclass(frozen=True)
class PersistencePaths:
    """Runtime paths for the one persistent self-hosting data boundary."""

    data_dir: Path = DEFAULT_DATA_DIR
    database: Path = DEFAULT_DB_PATH
    documents: Path = DEFAULT_DOCUMENTS_PATH
    backups: Path = DEFAULT_BACKUPS_PATH

    @property
    def directories(self) -> tuple[Path, ...]:
        return (self.data_dir, self.documents, self.backups)


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


def persistence_paths(
    *,
    data_dir: str | Path | None = None,
    database: str | Path | None = None,
    documents: str | Path | None = None,
    backups: str | Path | None = None,
) -> PersistencePaths:
    """Resolve runtime paths; defaults follow ADR-0014 below ``/data``."""
    configured_data_dir = data_dir or os.environ.get("LZUG_DATA_DIR")
    root = Path(configured_data_dir).expanduser() if configured_data_dir else DEFAULT_DATA_DIR
    if database is None:
        configured_database = os.environ.get("LZUG_DATABASE_PATH")
        configured_url = os.environ.get("LZUG_DATABASE_URL")
        if configured_database and configured_url:
            raise ValueError("Set only one of LZUG_DATABASE_URL and LZUG_DATABASE_PATH")
        database_value = configured_url or configured_database or root / "lzug.sqlite"
    else:
        database_value = database
    documents_value = documents if documents is not None else os.environ.get("LZUG_DOCUMENTS_PATH")
    backups_value = backups if backups is not None else os.environ.get("LZUG_BACKUPS_PATH")
    return PersistencePaths(
        data_dir=root,
        database=database_path(database_value),
        documents=Path(documents_value).expanduser() if documents_value else root / "documents",
        backups=Path(backups_value).expanduser() if backups_value else root / "backups",
    )


def _ensure_writable_directory(directory: Path) -> None:
    if directory.exists() and directory.is_symlink():
        raise PersistenceConfigurationError(
            f"Persistent directory must not be a symlink: {directory}"
        )
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise PersistenceConfigurationError(
            f"Persistent directory cannot be created: {directory} ({error})"
        ) from error
    if not directory.is_dir():
        raise PersistenceConfigurationError(f"Persistent path is not a directory: {directory}")
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".lzug-write-check-") as probe:
            probe.write(b"lzug")
            probe.flush()
            os.fsync(probe.fileno())
    except OSError as error:
        raise PersistenceConfigurationError(
            f"Persistent directory is not writable: {directory} ({error})"
        ) from error


def _ensure_writable_file(file_path: Path) -> None:
    try:
        descriptor = os.open(file_path, os.O_WRONLY | os.O_APPEND)
    except OSError as error:
        raise PersistenceConfigurationError(
            f"Persistent file is not writable: {file_path} ({error})"
        ) from error
    else:
        os.close(descriptor)


def _ensure_free_space(directory: Path, minimum_free_bytes: int) -> None:
    try:
        free_bytes = shutil.disk_usage(directory).free
    except OSError as error:
        raise PersistenceConfigurationError(
            f"Free space cannot be checked for {directory}: {error}"
        ) from error
    if free_bytes < minimum_free_bytes:
        raise PersistenceConfigurationError(
            f"Insufficient free space in {directory}: {free_bytes} bytes available, "
            f"at least {minimum_free_bytes} required"
        )


def validate_persistence(
    paths: PersistencePaths,
    *,
    minimum_free_bytes: int = DEFAULT_MIN_FREE_BYTES,
    require_database: bool = False,
) -> None:
    """Validate directories, write access, free space, and database shape."""
    if minimum_free_bytes < 0:
        raise ValueError("minimum_free_bytes must not be negative")
    checked_directories: set[Path] = set()
    for directory in (*paths.directories, paths.database.parent):
        _ensure_writable_directory(directory)
        resolved_directory = directory.resolve()
        if resolved_directory not in checked_directories:
            _ensure_free_space(directory, minimum_free_bytes)
            checked_directories.add(resolved_directory)

    if paths.database.is_symlink():
        raise PersistenceConfigurationError(
            f"Database path must not be a symlink: {paths.database}"
        )
    if paths.database.exists() and paths.database.is_dir():
        raise PersistenceConfigurationError(f"Database path is a directory: {paths.database}")
    if require_database and not paths.database.exists():
        raise PersistenceConfigurationError(f"Database does not exist: {paths.database}")
    if paths.database.exists():
        _ensure_writable_file(paths.database)


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
def connection_scope(db_path: Path = DEFAULT_DB_PATH) -> Iterator[Connection]:
    """Yield one connection and dispose its short-lived engine deterministically."""
    engine = engine_for(db_path)
    try:
        with engine.connect() as connection:
            yield connection
    finally:
        engine.dispose()


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
        if migration.name == "006_add_exam_execution_status.sql":
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
        with connection_scope(db_path) as connection:
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
        with connection_scope(db_path) as connection:
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
