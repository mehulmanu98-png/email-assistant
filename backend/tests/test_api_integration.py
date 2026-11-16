from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
import uuid

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import User, EmailAccount, EmailMessage, ReplyDraft


def login(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={
        "email": settings.bootstrap_email,
        "password": settings.bootstrap_password
    })
    assert response.status_code == 200


def test_dashboard_health_login_and_editable_sync_schedule():
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        assert health.json()["notifications"] is False

        assert client.get("/api/settings").status_code == 401
        login(client)

        settings_response = client.get("/api/settings")
        assert settings_response.status_code == 200
        assert settings_response.json()["timezone"] == "Asia/Kolkata"

        saved = client.patch("/api/settings", json={
            "sync_times": ["08:00", "11:00", "14:00", "17:00"],
            "timezone": "Asia/Kolkata"
        })
        assert saved.status_code == 200
        assert saved.json()["sync_times"] == ["08:00", "11:00", "14:00", "17:00"]
        assert saved.json()["ai_processing_enabled"] is False
        assert saved.json()["notifications_enabled"] is False

        invalid = client.patch("/api/settings", json={
            "sync_times": ["25:00"],
            "timezone": "Asia/Kolkata"
        })
        assert invalid.status_code == 422


def test_reply_send_requires_explicit_approval_and_keeps_draft():
    with TestClient(app) as client:
        login(client)
        db = SessionLocal()
        try:
            user = db.scalar(select(User).where(User.email == settings.bootstrap_email.lower()))
            assert user is not None
            account = EmailAccount(
                user_id=user.id, provider="icloud", email=f"test-{uuid.uuid4().hex}@example.com",
                connection_status="connected"
            )
            db.add(account)
            db.commit()
            db.refresh(account)

            source = EmailMessage(
                user_id=user.id, account_id=account.id,
                provider_message_id="<source@example.com>",
                thread_key="<source@example.com>",
                sender="sender@example.com",
                recipients=account.email,
                subject="Test source message",
                body_text="Original message"
            )
            db.add(source)
            db.commit()
            db.refresh(source)

            draft = ReplyDraft(
                user_id=user.id, message_id=source.id,
                to_json=["sender@example.com"], cc_json=[], bcc_json=[],
                subject="Re: Test source message", body="Approved test reply",
                status="draft"
            )
            db.add(draft)
            db.commit()
            db.refresh(draft)
            draft_id = draft.id
            expected_updated_at = draft.updated_at.isoformat()
        finally:
            db.close()

        response = client.post(f"/api/drafts/{draft_id}/send", json={
            "confirm_send": False,
            "expected_updated_at": expected_updated_at
        })
        assert response.status_code == 400
        assert "Explicit send confirmation" in response.json()["detail"]

        db = SessionLocal()
        try:
            saved_draft = db.get(ReplyDraft, draft_id)
            assert saved_draft is not None
            assert saved_draft.status == "draft"
        finally:
            db.close()


def test_followup_edit_snooze_complete_and_remove_preserve_source_email():
    with TestClient(app) as client:
        login(client)
        db = SessionLocal()
        try:
            user = db.scalar(select(User).where(User.email == settings.bootstrap_email.lower()))
            assert user is not None
            account = EmailAccount(
                user_id=user.id, provider="icloud",
                email=f"followup-{uuid.uuid4().hex}@example.com",
                connection_status="connected"
            )
            db.add(account)
            db.commit()
            db.refresh(account)

            source = EmailMessage(
                user_id=user.id, account_id=account.id,
                provider_message_id=f"<followup-{uuid.uuid4().hex}@example.com>",
                thread_key="<followup-thread@example.com>",
                sender="supplier@example.com", recipients=account.email,
                subject="Supplier confirmation", body_text="Please confirm dispatch.",
            )
            db.add(source)
            db.commit()
            db.refresh(source)
            source_id = source.id
        finally:
            db.close()

        created = client.post("/api/followups", json={
            "title": "Confirm supplier dispatch",
            "description": "Await dispatch confirmation.",
            "owner": "Supplier",
            "message_id": source_id,
            "status": "action_required",
        })
        assert created.status_code == 200
        followup_id = created.json()["id"]

        edited = client.patch(f"/api/followups/{followup_id}", json={
            "title": "Get dispatch date",
            "description": "Ask for the confirmed dispatch date.",
            "status": "awaiting_response",
        })
        assert edited.status_code == 200
        active = client.get("/api/followups")
        assert active.status_code == 200
        assert any(
            item["id"] == followup_id
            and item["title"] == "Get dispatch date"
            and item["status"] == "awaiting_response"
            for item in active.json()
        )

        until = datetime.now(timezone.utc) + timedelta(days=2)
        snoozed = client.patch(
            f"/api/followups/{followup_id}/snooze",
            params={"until": until.isoformat()},
        )
        assert snoozed.status_code == 200
        assert all(item["id"] != followup_id for item in client.get("/api/followups").json())

        unsnoozed = client.patch(f"/api/followups/{followup_id}", json={"snoozed_until": None})
        assert unsnoozed.status_code == 200
        assert any(item["id"] == followup_id for item in client.get("/api/followups").json())

        completed = client.patch(f"/api/followups/{followup_id}/complete")
        assert completed.status_code == 200
        assert all(item["id"] != followup_id for item in client.get("/api/followups").json())

        removed = client.delete(f"/api/followups/{followup_id}")
        assert removed.status_code == 200
        assert removed.json()["email_retained"] is True
        source_response = client.get(f"/api/messages/{source_id}")
        assert source_response.status_code == 200
        assert source_response.json()["body_text"] == "Please confirm dispatch."
