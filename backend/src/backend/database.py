"""SQLite engine setup, migration handling, and transaction-scoped sessions."""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from fcntl import LOCK_EX, LOCK_SH, LOCK_UN, flock
from functools import partial
from pathlib import Path

from sqlalchemy import MetaData, Table, create_engine, event, insert, inspect, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from .exam_venue_migration import (
    MIGRATION_NAME as EXAM_VENUE_MIGRATION,
)
from .exam_venue_migration import (
    ExamVenueMigrationConflictError,
    migrate_plan_reference_json,
    normalize_migration_text,
    prepare_exam_venue_migration,
)
from .models import Base
from .settings import PersistenceSettings, RuntimeSettings

COMPONENT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = Path("/data")
DEFAULT_DB_PATH = Path("/data/lzug.sqlite")
DEFAULT_DOCUMENTS_PATH = Path("/data/documents")
DEFAULT_BACKUPS_PATH = Path("/data/backups")
DEFAULT_MIN_FREE_BYTES = 64 * 1024 * 1024
BUSY_TIMEOUT_MS = 5_000
SQLITE_JOURNAL_MODE = "wal"
SQLITE_SYNCHRONOUS = 1
REQUIRED_TABLES = frozenset(Base.metadata.tables) | {
    "schema_migration",
    "schema_migration_checksum",
}
SCHEMA_PATH = COMPONENT_ROOT / "db" / "schema.sql"
MIGRATIONS_PATH = COMPONENT_ROOT / "db" / "migrations"


class PersistenceConfigurationError(RuntimeError):
    """Raised when persistent storage cannot serve the runtime."""


class MigrationError(PersistenceConfigurationError):
    """Raised when a database cannot be migrated to the application schema."""

    def __init__(self, message: str, *, reason: str = "migration_error") -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class MigrationRecord:
    """One safe-to-expose schema history entry."""

    name: str
    applied_at: str


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


def database_path(
    value: str | Path | None = None,
    *,
    settings: PersistenceSettings | None = None,
    environment: Mapping[str, str] | None = None,
) -> Path:
    """Resolve a SQLite file path from a CLI value or environment setting.

    ``sqlite:///`` URLs are accepted so deployment environments can expose one
    standard database setting while the application continues to pass a Path
    through its repository and service boundaries.
    """
    if value is None:
        configured = settings or RuntimeSettings.from_environment(environment).persistence
        database_url_value = configured.database_url
        database_path_value = configured.database_path_value
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
    settings: PersistenceSettings | None = None,
    environment: Mapping[str, str] | None = None,
    data_dir: str | Path | None = None,
    database: str | Path | None = None,
    documents: str | Path | None = None,
    backups: str | Path | None = None,
) -> PersistencePaths:
    """Resolve runtime paths; defaults follow ADR-0014 below ``/data``."""
    configured = settings or RuntimeSettings.from_environment(environment).persistence
    configured_data_dir = data_dir if data_dir is not None else configured.data_dir
    root = Path(configured_data_dir).expanduser() if configured_data_dir else DEFAULT_DATA_DIR
    if database is None:
        configured_database = configured.database_path_value
        configured_url = configured.database_url
        if configured_database and configured_url:
            raise ValueError("Set only one of LZUG_DATABASE_URL and LZUG_DATABASE_PATH")
        database_value = configured_url or configured_database or root / "lzug.sqlite"
    else:
        database_value = database
    documents_value = documents if documents is not None else configured.documents_path
    backups_value = backups if backups is not None else configured.backups_path
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


def _snapshot_lock_path(db_path: Path) -> Path:
    return Path(f"{db_path}.snapshot.lock")


def _activation_lock_path(db_path: Path) -> Path:
    return Path(f"{db_path}.activation.lock")


@contextmanager
def _file_lock(path: Path, operation: int) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as lock_file:
        flock(lock_file.fileno(), operation)
        try:
            yield
        finally:
            flock(lock_file.fileno(), LOCK_UN)


@contextmanager
def mutation_scope(db_path: Path = DEFAULT_DB_PATH) -> Iterator[None]:
    """Keep one database/document mutation outside an artifact snapshot or activation."""
    db_path = Path(db_path)
    with _file_lock(_activation_lock_path(db_path), LOCK_SH):
        with _file_lock(_snapshot_lock_path(db_path), LOCK_SH):
            yield


@contextmanager
def snapshot_scope(db_path: Path = DEFAULT_DB_PATH) -> Iterator[None]:
    """Wait for active mutations and prevent new ones while readers continue."""
    with _file_lock(_snapshot_lock_path(Path(db_path)), LOCK_EX):
        yield


@contextmanager
def activation_scope(db_path: Path = DEFAULT_DB_PATH) -> Iterator[None]:
    """Drain all application transactions before atomically activating a restore."""
    with _file_lock(_activation_lock_path(Path(db_path)), LOCK_EX):
        yield


def _is_mutating_statement(statement: str) -> bool:
    token = statement.lstrip().partition(" ")[0].partition("\n")[0].upper()
    return token in {
        "ALTER",
        "CREATE",
        "DELETE",
        "DROP",
        "INSERT",
        "REINDEX",
        "REPLACE",
        "UPDATE",
        "VACUUM",
    }


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
    db_path = Path(db_path)
    engine = engine_for(db_path)
    session_factory = sessionmaker(bind=engine, future=True)
    session = session_factory()
    snapshot_lock_path = _snapshot_lock_path(db_path)
    snapshot_lock_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_lock_file = snapshot_lock_path.open("a+")
    mutation_locked = False

    def lock_before_mutation(
        _connection, _cursor, statement, _parameters, _context, _executemany
    ) -> None:
        nonlocal mutation_locked
        if not mutation_locked and _is_mutating_statement(statement):
            flock(snapshot_lock_file.fileno(), LOCK_SH)
            mutation_locked = True

    event.listen(engine, "before_cursor_execute", lock_before_mutation)
    try:
        with _file_lock(_activation_lock_path(db_path), LOCK_SH):
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
    finally:
        session.close()
        event.remove(engine, "before_cursor_execute", lock_before_mutation)
        if mutation_locked:
            flock(snapshot_lock_file.fileno(), LOCK_UN)
        snapshot_lock_file.close()
        engine.dispose()


def _migration_files() -> tuple[Path, ...]:
    return tuple(
        sorted(
            migration
            for migration in MIGRATIONS_PATH.glob("[0-9][0-9][0-9]_*.sql")
            if not migration.name.startswith("000_")
        )
    )


def _migration_checksums() -> dict[str, str]:
    return {
        migration.name: hashlib.sha256(migration.read_bytes()).hexdigest()
        for migration in _migration_files()
    }


def _migration_table(connection: Connection) -> Table:
    tables = set(inspect(connection).get_table_names())
    if "schema_migration" not in tables:
        raise MigrationError(
            "Existing database has no versioned migration history; refusing to infer its schema."
        )
    table = Table("schema_migration", MetaData(), autoload_with=connection)
    columns = {column.name for column in table.columns}
    if not {"name", "applied_at"}.issubset(columns):
        raise MigrationError("Migration history table is incompatible with this application.")
    return table


def _migration_state(
    connection: Connection,
) -> tuple[tuple[MigrationRecord, ...], tuple[Path, ...]]:
    files = _migration_files()
    checksums = _migration_checksums()
    expected_names = tuple(migration.name for migration in files)
    table = _migration_table(connection)
    rows = connection.execute(select(table.c.name, table.c.applied_at)).all()
    names = tuple(row.name for row in rows)
    if len(set(names)) != len(names):
        raise MigrationError("Migration history contains duplicate entries.")
    unknown = sorted(set(names) - set(expected_names))
    if unknown:
        raise MigrationError(f"Migration history contains unknown entries: {', '.join(unknown)}.")
    prefix = expected_names[: len(names)]
    if set(names) != set(prefix):
        raise MigrationError("Migration history has a gap or was recorded out of order.")

    records_by_name = {row.name: MigrationRecord(row.name, str(row.applied_at)) for row in rows}
    if any(row.applied_at is None for row in rows):
        raise MigrationError("Migration history contains an entry without an application time.")
    records = tuple(records_by_name[name] for name in prefix)

    tables = set(inspect(connection).get_table_names())
    checksum_table = None
    if "schema_migration_checksum" in tables:
        checksum_table = Table("schema_migration_checksum", MetaData(), autoload_with=connection)
        checksum_columns = {column.name for column in checksum_table.columns}
        if not {"name", "checksum"}.issubset(checksum_columns):
            raise MigrationError("Migration checksum table is incompatible with this application.")
        checksum_rows = connection.execute(
            select(checksum_table.c.name, checksum_table.c.checksum)
        ).all()
        checksum_by_name = {row.name: row.checksum for row in checksum_rows}
        if len(checksum_by_name) != len(checksum_rows):
            raise MigrationError("Migration checksum history contains duplicate entries.")
        unknown_checksums = sorted(set(checksum_by_name) - set(expected_names))
        if unknown_checksums:
            raise MigrationError(
                "Migration checksum history contains unknown entries: "
                + ", ".join(unknown_checksums)
                + "."
            )
        for name, checksum in checksum_by_name.items():
            if checksum != checksums[name]:
                raise MigrationError(f"Checksum mismatch for migration {name}.")
        if "009_harden_migration_history.sql" in names:
            if set(checksum_by_name) != set(names):
                raise MigrationError("Migration checksum history is incomplete.")
    elif "009_harden_migration_history.sql" in names:
        raise MigrationError(
            "Migration history claims checksum protection without its metadata table."
        )

    pending = files[len(records) :]
    return records, pending


@contextmanager
def _migration_lock(db_path: Path) -> Iterator[None]:
    """Serialize migration and reset attempts across application processes."""
    lock_path = Path(f"{db_path}.migration.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock_file:
        flock(lock_file.fileno(), LOCK_EX)
        try:
            yield
        finally:
            flock(lock_file.fileno(), LOCK_UN)


def _migration_backup(
    db_path: Path,
    backup_dir: Path,
    *,
    backup_name: str | None = None,
) -> Path:
    if backup_dir.exists() and backup_dir.is_symlink():
        raise MigrationError("Migration backup directory must not be a symlink.")
    if backup_name is None:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup_path = backup_dir / f"{db_path.stem}.migration-{timestamp}.sqlite"
    else:
        candidate = Path(backup_name)
        if candidate != Path(candidate.name) or candidate.suffix != ".sqlite":
            raise MigrationError("Migration backup name must be a local SQLite filename.")
        backup_path = backup_dir / candidate
    temporary_path: Path | None = None
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=backup_dir, prefix=".lzug-migration-", suffix=".sqlite", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
        with closing(sqlite3.connect(str(db_path), timeout=BUSY_TIMEOUT_MS / 1000)) as source:
            with closing(sqlite3.connect(str(temporary_path))) as destination:
                source.backup(destination)
                destination.commit()
                integrity = destination.execute("PRAGMA integrity_check").fetchall()
                relations = destination.execute("PRAGMA foreign_key_check").fetchall()
                if integrity != [("ok",)] or relations:
                    raise MigrationError(
                        "Could not verify migration safety snapshot: database integrity failed."
                    )
        os.replace(temporary_path, backup_path)
        temporary_path = None
        return backup_path
    except MigrationError:
        raise
    except (OSError, sqlite3.Error) as error:
        raise MigrationError(f"Could not create migration safety snapshot: {error}") from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _record_migration(engine: Engine, migration: Path) -> None:
    table = None
    with engine.begin() as connection:
        table = _migration_table(connection)
        existing = connection.execute(
            select(table.c.name).where(table.c.name == migration.name)
        ).first()
        if existing is None:
            raise MigrationError(
                f"Migration {migration.name} committed without recording its history."
            )

        if "schema_migration_checksum" in inspect(connection).get_table_names():
            checksum_table = Table(
                "schema_migration_checksum", MetaData(), autoload_with=connection
            )
            checksums = _migration_checksums()
            applied_names = connection.scalars(select(table.c.name)).all()
            existing_checksums = set(connection.scalars(select(checksum_table.c.name)))
            for name in applied_names:
                if name not in existing_checksums:
                    connection.execute(
                        insert(checksum_table).values(name=name, checksum=checksums[name])
                    )


def _apply_migrations_unlocked(
    db_path: Path,
    backup_dir: Path | None = None,
    *,
    migration_backup_name: str | None = None,
    migration_timestamp: str | None = None,
) -> None:
    if not db_path.exists() or db_path.stat().st_size == 0:
        raise MigrationError(
            "Cannot migrate a missing or empty database.", reason="database_missing"
        )
    engine = engine_for(db_path)
    try:
        with engine.connect() as connection:
            _records, pending = _migration_state(connection)
        backup_path = None
        effective_backup_dir = backup_dir or db_path.parent / "backups"
        if pending:
            backup_path = _migration_backup(
                db_path,
                effective_backup_dir,
                backup_name=migration_backup_name,
            )
        for migration in pending:
            venue_preparation = None
            if migration.name == EXAM_VENUE_MIGRATION:
                if backup_path is None:
                    raise MigrationError("Exam-venue migration requires a verified backup.")
                try:
                    venue_preparation = prepare_exam_venue_migration(
                        db_path, backup_path, effective_backup_dir
                    )
                except ExamVenueMigrationConflictError as error:
                    raise MigrationError(str(error), reason="migration_conflict") from error
            raw_connection = engine.raw_connection()
            try:
                raw_connection.create_function(
                    "lzug_normalize", 1, normalize_migration_text, deterministic=True
                )
                raw_connection.create_function(
                    "lzug_migrate_plan_json", 1, migrate_plan_reference_json, deterministic=True
                )
                if venue_preparation is not None:
                    raw_connection.create_function(
                        "lzug_migration_timestamp",
                        0,
                        lambda: migration_timestamp or datetime.now(UTC).isoformat(),
                    )
                    raw_connection.create_function(
                        "lzug_migration_backup",
                        0,
                        partial(str, venue_preparation.backup_reference),
                    )
                    raw_connection.create_function(
                        "lzug_migration_report_json",
                        0,
                        partial(str, venue_preparation.machine_report),
                    )
                    raw_connection.create_function(
                        "lzug_migration_report_text",
                        0,
                        partial(str, venue_preparation.human_report),
                    )
                raw_connection.executescript(migration.read_text(encoding="utf-8"))
                raw_connection.commit()
            except (OSError, sqlite3.Error) as error:
                try:
                    raw_connection.rollback()
                except sqlite3.Error:
                    pass
                raise MigrationError(f"Migration {migration.name} failed: {error}") from error
            finally:
                raw_connection.close()
            try:
                _record_migration(engine, migration)
            except MigrationError:
                raise
            except (OSError, SQLAlchemyError) as error:
                raise MigrationError(
                    f"Migration {migration.name} history could not be recorded: {error}"
                ) from error
        with engine.connect() as connection:
            _migration_state(connection)
    finally:
        engine.dispose()


def initialize(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    seed_sql: str | None = None,
    seed_path: Path | None = None,
    reset: bool = False,
    backup_dir: Path | None = None,
    migration_backup_name: str | None = None,
    migration_timestamp: str | None = None,
) -> None:
    if seed_sql is not None and seed_path is not None:
        raise PersistenceConfigurationError("Provide either seed_sql or seed_path, not both")
    db_path = Path(db_path)
    with _migration_lock(db_path):
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
                raw_connection.commit()
            except (OSError, sqlite3.Error) as error:
                try:
                    raw_connection.rollback()
                except sqlite3.Error:
                    pass
                raise MigrationError(f"Initial schema creation failed: {error}") from error
            finally:
                raw_connection.close()
                engine.dispose()

        _apply_migrations_unlocked(
            db_path,
            backup_dir,
            migration_backup_name=migration_backup_name,
            migration_timestamp=migration_timestamp,
        )

        if is_new_database and (seed_sql is not None or seed_path is not None):
            engine = engine_for(db_path)
            raw_connection = engine.raw_connection()
            try:
                seed_text = (
                    seed_sql
                    if seed_sql is not None
                    else Path(seed_path).read_text(encoding="utf-8")
                )
                # Seed compilation is allowed to order records for readability
                # rather than reproducing the schema's complete FK topology.
                # Disable enforcement only for this one disposable import.
                raw_connection.execute("PRAGMA foreign_keys = OFF")
                raw_connection.execute("PRAGMA defer_foreign_keys = ON")
                raw_connection.executescript(seed_text)
                raw_connection.commit()
                raw_connection.execute("PRAGMA foreign_keys = ON")
            except (OSError, sqlite3.Error) as error:
                try:
                    raw_connection.rollback()
                except sqlite3.Error:
                    pass
                raise MigrationError(f"Initial seed creation failed: {error}") from error
            finally:
                raw_connection.close()
                engine.dispose()


def apply_migrations(
    db_path: Path = DEFAULT_DB_PATH,
    backup_dir: Path | None = None,
) -> None:
    db_path = Path(db_path)
    with _migration_lock(db_path):
        _apply_migrations_unlocked(db_path, backup_dir)


def migration_status(db_path: Path = DEFAULT_DB_PATH) -> dict[str, object]:
    """Return migration diagnostics containing only schema metadata."""
    files = _migration_files()
    target = files[-1].name if files else None
    if not db_path.exists() or db_path.stat().st_size == 0:
        return {
            "state": "database_missing",
            "current": None,
            "target": target,
            "pending": [migration.name for migration in files],
            "history": [],
        }
    engine = engine_for(db_path)
    try:
        with engine.connect() as connection:
            records, pending = _migration_state(connection)
        return {
            "state": "migration_required" if pending else "ready",
            "current": records[-1].name if records else None,
            "target": target,
            "pending": [migration.name for migration in pending],
            "history": [
                {"name": record.name, "applied_at": record.applied_at} for record in records
            ],
        }
    except MigrationError, OSError, SQLAlchemyError:
        return {
            "state": "migration_error",
            "current": None,
            "target": target,
            "pending": [],
            "history": [],
        }
    finally:
        engine.dispose()


def database_readiness(db_path: Path = DEFAULT_DB_PATH) -> dict[str, object]:
    """Return safe readiness and migration diagnostics for startup and health checks."""
    migration = migration_status(db_path)
    if migration["state"] != "ready":
        return {"ready": False, "reason": migration["state"], "migration": migration}
    try:
        with connection_scope(db_path) as connection:
            tables = inspect(connection)
            if not REQUIRED_TABLES.issubset(set(tables.get_table_names())):
                return {"ready": False, "reason": "schema_incomplete", "migration": migration}
            settings = sqlite_settings(connection)
            if settings != {
                "foreign_keys": 1,
                "journal_mode": SQLITE_JOURNAL_MODE,
                "synchronous": SQLITE_SYNCHRONOUS,
                "busy_timeout": BUSY_TIMEOUT_MS,
            }:
                return {"ready": False, "reason": "sqlite_settings_invalid", "migration": migration}
    except OSError, RuntimeError, SQLAlchemyError:
        return {"ready": False, "reason": "database_unavailable", "migration": migration}
    return {"ready": True, "reason": "ready", "migration": migration}


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
    return bool(database_readiness(db_path)["ready"])
