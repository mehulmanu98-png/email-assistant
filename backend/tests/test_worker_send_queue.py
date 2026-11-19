from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import User, EmailAccount, OutboundDraft
import app.worker as worker


def _worker_db(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(worker, "SessionLocal", factory)
    db = factory()
    user = User(email="owner@example.com", password_hash="test-hash")
    db.add(user)
    db.commit()
    account = EmailAccount(
        user_id=user.id,
        provider="icloud",
        email="owner@icloud.com",
        encrypted_secret="encrypted-placeholder",
        connection_status="connected",
    )
    db.add(account)
    db.commit()
    draft = OutboundDraft(
        user_id=user.id,
        account_id=account.id,
        to_json=["recipient@example.com"],
        cc_json=[],
        bcc_json=[],
        subject="Approved test",
        body="This is a test.",
        status="queued",
    )
    db.add(draft)
    db.commit()
    draft_id = draft.id
    db.close()
    return engine, factory, draft_id


def test_approved_outbound_draft_is_sent_once_by_worker(monkeypatch):
    engine, factory, draft_id = _worker_db(monkeypatch)
    sent = []

    def fake_send(account, to, cc, bcc, subject, body, source, attachments=None):
        sent.append((account.email, to, subject, body))
        return "<provider-message-id>"

    monkeypatch.setattr(worker, "send_icloud", fake_send)

    assert worker.run_send_once() is True
    assert worker.run_send_once() is False

    db = factory()
    draft = db.get(OutboundDraft, draft_id)
    assert draft.status == "sent"
    assert draft.provider_sent_id == "<provider-message-id>"
    assert len(sent) == 1
    db.close()
    engine.dispose()


def test_ambiguous_provider_result_is_not_automatically_retried(monkeypatch):
    engine, factory, draft_id = _worker_db(monkeypatch)
    calls = []

    def failed_send(*args, **kwargs):
        calls.append(True)
        raise TimeoutError("provider timeout")

    monkeypatch.setattr(worker, "send_icloud", failed_send)

    assert worker.run_send_once() is True
    assert worker.run_send_once() is False

    db = factory()
    draft = db.get(OutboundDraft, draft_id)
    assert draft.status == "send_uncertain"
    assert len(calls) == 1
    db.close()
    engine.dispose()
