from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def _add_missing_columns() -> None:
    """Minimal poor-man's migration: `create_all()` only creates missing
    *tables*, never missing *columns* on tables that already exist. There's
    no Alembic in this project yet, so when a column is added to an
    existing model (e.g. `Modification.is_binary`), add it here too —
    this keeps already-running local/dev databases (and their existing
    projects) working without requiring a manual reset."""
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            existing_columns = {
                row[1] for row in conn.execute(text(f'PRAGMA table_info("{table.name}")'))
            }
            for column in table.columns:
                if column.name in existing_columns:
                    continue
                col_type = column.type.compile(engine.dialect)
                default_sql = ""
                if column.name == "is_binary":
                    default_sql = " DEFAULT 0"
                conn.execute(
                    text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}{default_sql}')
                )
        conn.commit()


def init_db() -> None:
    from app.models import assistant, job, modification, project  # noqa: F401 (registers tables)

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
