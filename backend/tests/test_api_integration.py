from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
import uuid

from app.config import settings
from app.db import SessionLocal
from app.main import app
import app.main as main_module
from app.models import User, EmailAccount, EmailMessage, ReplyDraft, AIConversation
from app.conversation_sync import append_linked_email_messages, canonical_thread_key


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


def test_email_thread_link_backfills_updates_once_and_preserves_history_on_unlink():
    with TestClient(app) as client:
        login(client)
        db = SessionLocal()
        try:
            user = db.scalar(select(User).where(User.email == settings.bootstrap_email.lower()))
            assert user is not None
            account = EmailAccount(
                user_id=user.id, provider="gmail",
                email=f"thread-{uuid.uuid4().hex}@example.com",
                connection_status="connected"
            )
            db.add(account)
            db.commit()
            db.refresh(account)

            conversation = AIConversation(user_id=user.id, title="Supplier thread", messages=[])
            db.add(conversation)
            db.commit()
            db.refresh(conversation)

            first = EmailMessage(
                user_id=user.id, account_id=account.id,
                provider_message_id="provider-msg-1", thread_key="gmail-thread-1",
                sender="supplier@example.com", recipients=account.email,
                subject="Dispatch plan", body_text="First update",
            )
            second = EmailMessage(
                user_id=user.id, account_id=account.id,
                provider_message_id="provider-msg-2", thread_key="gmail-thread-1",
                sender="supplier@example.com", recipients=account.email,
                subject="Re: Dispatch plan", body_text="Second update",
            )
            db.add_all([first, second])
            db.commit()
            db.refresh(first)
            db.refresh(second)
            account_id = account.id
            conversation_id = conversation.id
            first_id = first.id
        finally:
            db.close()

        linked = client.post(f"/api/messages/{first_id}/conversation", json={
            "conversation_id": conversation_id,
            "auto_update": True,
        })
        assert linked.status_code == 200
        assert linked.json()["appended_messages"] == 2
        assert linked.json()["thread_message_count"] == 2

        details = client.get(f"/api/conversations/{conversation_id}")
        assert details.status_code == 200
        email_items = [m for m in details.json()["messages"] if m.get("kind") == "email_context"]
        assert len(email_items) == 2
        assert all("untrusted sender-supplied content" in item["content"] for item in email_items)

        repeated = client.post(f"/api/messages/{first_id}/conversation", json={
            "conversation_id": conversation_id,
            "auto_update": True,
        })
        assert repeated.status_code == 200
        assert repeated.json()["appended_messages"] == 0
        assert len(client.get(f"/api/conversations/{conversation_id}").json()["messages"]) == 2

        db = SessionLocal()
        try:
            user = db.scalar(select(User).where(User.email == settings.bootstrap_email.lower()))
            account = db.get(EmailAccount, account_id)
            third = EmailMessage(
                user_id=user.id, account_id=account_id,
                provider_message_id="provider-msg-3", thread_key="gmail-thread-1",
                sender="supplier@example.com", recipients=account.email,
                subject="Re: Dispatch plan", body_text="Third update",
            )
            db.add(third)
            db.commit()
        finally:
            db.close()

        db = SessionLocal()
        try:
            assert append_linked_email_messages(db, account_id) == 1
            db.commit()
            assert append_linked_email_messages(db, account_id) == 0
            db.commit()
        finally:
            db.close()

        after_sync = client.get(f"/api/conversations/{conversation_id}").json()["messages"]
        assert len([m for m in after_sync if m.get("kind") == "email_context"]) == 3

        unlinked = client.delete(f"/api/messages/{first_id}/conversation")
        assert unlinked.status_code == 200
        assert unlinked.json()["conversation_history_retained"] is True

        db = SessionLocal()
        try:
            user = db.scalar(select(User).where(User.email == settings.bootstrap_email.lower()))
            account = db.get(EmailAccount, account_id)
            fourth = EmailMessage(
                user_id=user.id, account_id=account_id,
                provider_message_id="provider-msg-4", thread_key="gmail-thread-1",
                sender="supplier@example.com", recipients=account.email,
                subject="Re: Dispatch plan", body_text="Fourth update",
            )
            db.add(fourth)
            db.commit()
        finally:
            db.close()

        db = SessionLocal()
        try:
            assert append_linked_email_messages(db, account_id) == 0
        finally:
            db.close()

        relinked = client.post(f"/api/messages/{first_id}/conversation", json={
            "conversation_id": conversation_id,
            "auto_update": True,
        })
        assert relinked.status_code == 200
        assert relinked.json()["appended_messages"] == 1

        final_messages = client.get(f"/api/conversations/{conversation_id}").json()["messages"]
        assert len([m for m in final_messages if m.get("kind") == "email_context"]) == 4
        assert sum("First update" in m["content"] for m in final_messages if m.get("kind") == "email_context") == 1

        other_conversation = client.post("/api/conversations", json={"title": "Different destination"})
        assert other_conversation.status_code == 200
        conflict = client.post(f"/api/messages/{first_id}/conversation", json={
            "conversation_id": other_conversation.json()["id"],
            "auto_update": True,
        })
        assert conflict.status_code == 409


def test_icloud_reference_header_resolves_to_stable_root_message_id():
    from app.models import EmailAccount, EmailMessage
    from app.conversation_sync import canonical_thread_key
    from app.db import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = factory()
    try:
        user = User(email=f"icloud-{uuid.uuid4().hex}@example.com", password_hash="unused")
        db.add(user)
        db.commit()
        db.refresh(user)
        account = EmailAccount(
            user_id=user.id, provider="icloud",
            email=f"icloud-{uuid.uuid4().hex}@example.com",
            connection_status="connected",
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        root = EmailMessage(
            user_id=user.id, account_id=account.id,
            provider_message_id="<root@example.com>",
            thread_key="<root@example.com>",
            sender="sender@example.com", subject="Original",
        )
        reply = EmailMessage(
            user_id=user.id, account_id=account.id,
            provider_message_id="<reply@example.com>",
            thread_key="<root@example.com> <reply@example.com>",
            sender="sender@example.com", subject="Reply",
        )
        db.add_all([root, reply])
        db.commit()
        db.refresh(account)
        db.refresh(reply)
        assert canonical_thread_key(db, account, reply) == "<root@example.com>"
    finally:
        db.close()
        engine.dispose()


def test_waiting_for_user_tasks_do_not_consume_active_execution_slots():
    with TestClient(app) as client:
        login(client)
        for index in range(4):
            created = client.post("/api/tasks", json={
                "title": f"Pending approval task {index + 1}",
                "instructions": "Wait until the approved AI integration is available.",
                "priority": "normal",
            })
            assert created.status_code == 200
            assert created.json()["status"] == "waiting_for_user"

        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["active_tasks"] == 0


def test_original_attachment_view_does_not_change_email_read_state(monkeypatch):
    with TestClient(app) as client:
        login(client)
        db = SessionLocal()
        try:
            user = db.scalar(select(User).where(User.email == settings.bootstrap_email.lower()))
            account = EmailAccount(
                user_id=user.id, provider="gmail",
                email=f"attachment-{uuid.uuid4().hex}@example.com",
                connection_status="connected",
            )
            db.add(account)
            db.commit()
            db.refresh(account)
            source = EmailMessage(
                user_id=user.id, account_id=account.id,
                provider_message_id="gmail-attachment-source",
                thread_key="gmail-attachment-thread",
                sender="sender@example.com", recipients=account.email,
                subject="Invoice attached", body_text="Please see the attached invoice.",
                is_read=False, has_attachments=True,
            )
            db.add(source)
            db.commit()
            db.refresh(source)
            message_id = source.id
        finally:
            db.close()

        monkeypatch.setattr(main_module, "list_gmail_attachments", lambda *args: [{
            "index": 0, "filename": "invoice.pdf", "mime_type": "application/pdf",
            "size": 8, "is_inline": False, "can_preview": True, "available": True,
        }])
        monkeypatch.setattr(main_module, "get_gmail_attachment", lambda *args: {
            "filename": "invoice.pdf", "mime_type": "application/pdf",
            "size": 8, "is_inline": False, "data": b"%PDFtest",
        })

        listed = client.get(f"/api/messages/{message_id}/attachments")
        assert listed.status_code == 200
        assert listed.json()["attachments"][0]["filename"] == "invoice.pdf"

        previewed = client.get(f"/api/messages/{message_id}/attachments/0?inline=true")
        assert previewed.status_code == 200
        assert previewed.headers["content-type"] == "application/pdf"
        assert previewed.headers["content-disposition"].startswith("inline;")
        assert previewed.content == b"%PDFtest"

        db = SessionLocal()
        try:
            stored = db.get(EmailMessage, message_id)
            assert stored is not None
            assert stored.is_read is False
        finally:
            db.close()
