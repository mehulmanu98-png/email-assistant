from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings

class Base(DeclarativeBase):
    pass

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

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
    _add_missing_columns("email_accounts", {
        "icloud_sync_uid_cursor": "VARCHAR(128)",
        "icloud_sync_since": "VARCHAR(32)",
        "gmail_sync_page_token": "TEXT",
        "gmail_sync_query": "TEXT"
    })
