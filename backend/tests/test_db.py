from app.db import normalize_database_url

def test_neon_postgres_url_uses_psycopg_and_tls():
    url = normalize_database_url("postgresql://person:secret@ep-example-pooler.neon.tech/appdb")
    assert url.drivername == "postgresql+psycopg"
    assert url.query["sslmode"] == "require"
    assert url.host == "ep-example-pooler.neon.tech"

def test_explicit_postgres_driver_settings_are_preserved():
    url = normalize_database_url("postgresql+psycopg://person:secret@host/db?sslmode=verify-full")
    assert url.drivername == "postgresql+psycopg"
    assert url.query["sslmode"] == "verify-full"

def test_sqlite_url_is_unchanged():
    url = normalize_database_url("sqlite:///./mail.db")
    assert url.drivername == "sqlite"
