from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings


def normalize_database_url(value: str):
    """Make provider-supplied PostgreSQL URLs compatible with psycopg 3 and TLS."""
    url = make_url(value.strip())
    if url.get_backend_name() == "postgresql":
        if url.drivername == "postgresql":
            url = url.set(drivername="postgresql+psycopg")
        query = dict(url.query)
        query.setdefault("sslmode", "require")
        url = url.set(query=query)
    return url


DATABASE_URL = normalize_database_url(settings.database_url)
engine_options = {"pool_pre_ping": True}
if DATABASE_URL.get_backend_name() == "sqlite":
    engine_options["connect_args"] = {"check_same_thread": False}
else:
    engine_options.update({"pool_size": 2, "max_overflow": 2, "pool_timeout": 30, "pool_recycle": 300})
engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _add_missing_columns(table: str, definitions: dict[str, str]) -> None:
    existing = {column["name"] for column in inspect(engine).get_columns(table)}
    missing = [(name, sql_type) for name, sql_type in definitions.items() if name not in existing]
    if missing:
        with engine.begin() as connection:
            for name, sql_type in missing:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))


def init_db():
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _add_missing_columns("reply_drafts", {"provider_sent_id": "VARCHAR(500)"})
    _add_missing_columns("outbound_drafts", {"attachments_json": "JSONB" if DATABASE_URL.get_backend_name() == "postgresql" else "JSON"})
    _add_missing_columns("email_messages", {"is_starred": "BOOLEAN NOT NULL DEFAULT FALSE", "attachment_summary": "TEXT NOT NULL DEFAULT ''", "body_html": "TEXT NOT NULL DEFAULT ''"})
    sync_time_type = "TIMESTAMP WITH TIME ZONE" if DATABASE_URL.get_backend_name() == "postgresql" else "DATETIME"
    _add_missing_columns("sync_jobs", {
        "attempt_count": "INTEGER NOT NULL DEFAULT 0",
        "available_at": sync_time_type
    })
    _add_missing_columns("email_accounts", {
        "icloud_sync_uid_cursor": "VARCHAR(128)",
        "icloud_sync_since": "VARCHAR(32)",
        "icloud_sync_uidvalidity": "VARCHAR(128)",
        "gmail_sync_page_token": "TEXT",
        "gmail_sync_query": "TEXT"
    })
