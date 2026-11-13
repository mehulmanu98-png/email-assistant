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

def init_db():
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    # Additive migration for installations created by the earlier foundation release.
    columns = {c["name"] for c in inspect(engine).get_columns("reply_drafts")}
    if "provider_sent_id" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE reply_drafts ADD COLUMN provider_sent_id VARCHAR(500)"))
