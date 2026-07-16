from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import MetaData, Table, create_engine, event, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT_DIR / "var" / "lzug.sqlite3"
SCHEMA_PATH = ROOT_DIR / "db" / "schema.sql"
SEED_PATH = ROOT_DIR / "db" / "seed_demo.sql"
MIGRATIONS_PATH = ROOT_DIR / "db" / "migrations"


def database_url(db_path: Path = DEFAULT_DB_PATH) -> str:
    return f"sqlite:///{db_path}"


def engine_for(db_path: Path = DEFAULT_DB_PATH) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url(db_path), future=True, poolclass=NullPool)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine


def connect(db_path: Path = DEFAULT_DB_PATH) -> Connection:
    return engine_for(db_path).connect()


@contextmanager
def session_scope(db_path: Path = DEFAULT_DB_PATH) -> Iterator[Session]:
    session_factory = sessionmaker(bind=engine_for(db_path), future=True)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def initialize(
    db_path: Path = DEFAULT_DB_PATH,
    with_seed: bool = False,
    reset: bool = False,
) -> None:
    if reset:
        db_path.unlink(missing_ok=True)

    is_new_database = not db_path.exists()
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
        raw_connection = engine.raw_connection()
        try:
            raw_connection.executescript(migration.read_text(encoding="utf-8"))
            raw_connection.commit()
        finally:
            raw_connection.close()

    engine.dispose()


def is_available(db_path: Path = DEFAULT_DB_PATH) -> bool:
    with connect(db_path) as connection:
        connection.execute(select(1))
    return True
