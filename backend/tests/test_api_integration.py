from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
import uuid

from app.config import settings
from app.db import SessionLocal
from app.main import app
import app.main as main_module
from app.models import User, EmailAccount, EmailMessage, ReplyDraft, ForwardDraft, OutboundDraft, FollowUp, SyncJob, AIConversation, AppleDevice, AppleDeviceCommand
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
            "sync_times": ["08:00", "12:00", "17:00"],
            "timezone": "Asia/Kolkata"
        })
        assert saved.status_code == 200
        assert saved.json()["sync_times"] == ["08:00", "12:00", "17:00"]
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

        dashboard = client.get("/api/dashboard")
        assert dashboard.status_code == 200
        assert dashboard.json()["active_tasks"] == 0


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


def test_forward_draft_uses_source_account_separate_thread_and_explicit_approval(monkeypatch):
    with TestClient(app) as client:
        login(client)
        db = SessionLocal()
        try:
            user = db.scalar(select(User).where(User.email == settings.bootstrap_email.lower()))
            account = EmailAccount(
                user_id=user.id, provider="gmail",
                email=f"forward-{uuid.uuid4().hex}@example.com",
                connection_status="connected",
            )
            db.add(account)
            db.commit()
            db.refresh(account)
            source = EmailMessage(
                user_id=user.id, account_id=account.id,
                provider_message_id="gmail-forward-source",
                thread_key="gmail-original-thread",
                sender="sender@example.com", recipients=account.email,
                subject="Original contract", body_text="Original contract body",
                has_attachments=True,
            )
            db.add(source)
            db.commit()
            db.refresh(source)
            message_id = source.id
            source_account = account.email
        finally:
            db.close()

        created = client.post(f"/api/messages/{message_id}/forward")
        assert created.status_code == 200
        forward = created.json()
        assert forward["from_account"] == source_account
        assert forward["to"] == []
        assert forward["include_attachments"] is True
        assert forward["subject"] == "Fwd: Original contract"

        saved = client.patch(f"/api/forward-drafts/{forward['id']}", json={
            "to": ["recipient@example.com"],
            "cc": [],
            "bcc": [],
            "subject": forward["subject"],
            "body": "Please review this.",
            "include_attachments": True,
        })
        assert saved.status_code == 200

        denied = client.post(f"/api/forward-drafts/{forward['id']}/send", json={
            "confirm_send": False,
            "expected_updated_at": saved.json()["updated_at"],
        })
        assert denied.status_code == 400

        calls = []
        def fake_send(db_arg, account_arg, to, cc, bcc, subject, cover, source_arg, include_attachments):
            calls.append((account_arg.email, to, subject, cover, source_arg.thread_key, include_attachments))
            return "gmail-forwarded-message-id"
        monkeypatch.setattr(main_module, "send_gmail_forward", fake_send)

        sent = client.post(f"/api/forward-drafts/{forward['id']}/send", json={
            "confirm_send": True,
            "expected_updated_at": saved.json()["updated_at"],
        })
        assert sent.status_code == 200
        assert sent.json()["provider_accepted"] is True
        assert sent.json()["delivery_confirmed"] is False
        assert calls == [(
            source_account, ["recipient@example.com"], "Fwd: Original contract",
            "Please review this.", "gmail-original-thread", True
        )]

        db = SessionLocal()
        try:
            stored = db.get(ForwardDraft, forward["id"])
            assert stored is not None
            assert stored.status == "sent"
            assert stored.provider_sent_id == "gmail-forwarded-message-id"
        finally:
            db.close()


def test_forward_creation_is_blocked_while_prior_send_result_is_uncertain():
    with TestClient(app) as client:
        login(client)
        db = SessionLocal()
        try:
            user = db.scalar(select(User).where(User.email == settings.bootstrap_email.lower()))
            account = EmailAccount(
                user_id=user.id, provider="gmail",
                email=f"forward-uncertain-{uuid.uuid4().hex}@example.com",
                connection_status="connected",
            )
            db.add(account)
            db.commit()
            db.refresh(account)
            source = EmailMessage(
                user_id=user.id, account_id=account.id,
                provider_message_id="gmail-forward-uncertain-source",
                thread_key="gmail-forward-uncertain-thread",
                sender="sender@example.com", recipients=account.email,
                subject="Order confirmation", body_text="Original order details.",
            )
            db.add(source)
            db.commit()
            db.refresh(source)
            message_id = source.id
        finally:
            db.close()

        created = client.post(f"/api/messages/{message_id}/forward")
        assert created.status_code == 200
        db = SessionLocal()
        try:
            draft = db.get(ForwardDraft, created.json()["id"])
            assert draft is not None
            draft.status = "send_uncertain"
            db.commit()
        finally:
            db.close()

        blocked = client.post(f"/api/messages/{message_id}/forward")
        assert blocked.status_code == 409
        assert "Sent folder" in blocked.json()["detail"]


def test_apple_device_enrollment_command_lease_and_confirmed_native_receipt():
    with TestClient(app) as client:
        login(client)
        enrollment = client.post("/api/apple/devices/enrollment", json={
            "device_name": "Mehul MacBook",
        })
        assert enrollment.status_code == 200
        enrollment_token = enrollment.json()["enrollment_token"]

        enrolled = client.post("/api/apple/device/enroll", json={
            "enrollment_token": enrollment_token,
            "device_name": "Mehul MacBook",
        })
        assert enrolled.status_code == 200
        device_token = enrolled.json()["device_token"]
        device_id = enrolled.json()["device_id"]

        reused = client.post("/api/apple/device/enroll", json={
            "enrollment_token": enrollment_token,
            "device_name": "Second device",
        })
        assert reused.status_code == 401

        devices = client.get("/api/apple/devices")
        assert devices.status_code == 200
        assert devices.json()[0]["id"] == device_id
        assert "token_hash" not in devices.json()[0]
        assert "device_token" not in devices.json()[0]

        command_data = {
            "command_type": "note",
            "title": "Supplier quotation",
            "body": "Review the revised extrusion lamination quotation.",
            "timezone": "Asia/Kolkata",
            "idempotency_key": str(uuid.uuid4()),
        }
        queued = client.post("/api/apple/commands", json=command_data)
        assert queued.status_code == 200
        command_id = queued.json()["id"]
        assert queued.json()["status"] == "pending_on_device"

        duplicate = client.post("/api/apple/commands", json=command_data)
        assert duplicate.status_code == 200
        assert duplicate.json()["id"] == command_id

        pending = client.get("/api/apple/commands").json()
        assert any(item["id"] == command_id and item["status"] == "pending_on_device" for item in pending)

        headers = {"X-Apple-Device-Token": device_token}
        polled = client.post("/api/apple/device/commands/poll", headers=headers)
        assert polled.status_code == 200
        lease = polled.json()["commands"][0]
        assert lease["id"] == command_id
        assert lease["command_type"] == "note"
        assert lease["payload"]["title"] == "Supplier quotation"
        assert lease["lease_token"]

        leased = client.get("/api/apple/commands").json()
        assert next(item for item in leased if item["id"] == command_id)["status"] == "leased"

        completed = client.post(
            f"/api/apple/device/commands/{command_id}/result",
            headers=headers,
            json={
                "lease_token": lease["lease_token"],
                "success": True,
                "native_record_id": "apple-note-id-123",
            },
        )
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"
        assert completed.json()["result"]["native_record_id"] == "apple-note-id-123"
        assert completed.json()["completed_at"] is not None

        replay = client.post(
            f"/api/apple/device/commands/{command_id}/result",
            headers=headers,
            json={
                "lease_token": lease["lease_token"],
                "success": True,
                "native_record_id": "apple-note-id-123",
            },
        )
        assert replay.status_code == 404

        revoked = client.delete(f"/api/apple/devices/{device_id}")
        assert revoked.status_code == 200
        rejected_poll = client.post("/api/apple/device/commands/poll", headers=headers)
        assert rejected_poll.status_code == 401


def test_apple_reminder_requires_due_time_and_uses_idempotency():
    with TestClient(app) as client:
        login(client)
        invalid = client.post("/api/apple/commands", json={
            "command_type": "reminder",
            "title": "Call supplier",
            "timezone": "Asia/Kolkata",
            "idempotency_key": str(uuid.uuid4()),
        })
        assert invalid.status_code == 422
        valid = client.post("/api/apple/commands", json={
            "command_type": "reminder",
            "title": "Call supplier",
            "body": "Discuss delivery schedule.",
            "due_at": "2026-11-17T15:30:00",
            "timezone": "Asia/Kolkata",
            "idempotency_key": str(uuid.uuid4()),
        })
        assert valid.status_code == 200
        assert valid.json()["status"] == "pending_on_device"
        assert valid.json()["payload"]["due_at"].endswith("+00:00")


def test_read_state_can_mark_email_read_and_unread_only_after_provider_confirmation(monkeypatch):
    calls = []

    def fake_set_read(db, account, provider_message_id, is_read):
        calls.append((account.provider, provider_message_id, is_read))
        return True

    monkeypatch.setattr(main_module, "set_gmail_read", fake_set_read)

    with TestClient(app) as client:
        login(client)
        db = SessionLocal()
        try:
            user = db.scalar(select(User).where(User.email == settings.bootstrap_email.lower()))
            account = EmailAccount(
                user_id=user.id, provider="gmail",
                email=f"read-state-{uuid.uuid4().hex}@example.com",
                connection_status="connected"
            )
            db.add(account)
            db.commit()
            db.refresh(account)
            source = EmailMessage(
                user_id=user.id, account_id=account.id,
                provider_message_id="gmail-read-state-message",
                thread_key="gmail-read-state-thread",
                sender="sender@example.com", recipients=account.email,
                subject="Read state test", body_text="Test body", is_read=True,
            )
            db.add(source)
            db.commit()
            db.refresh(source)
            message_id = source.id
        finally:
            db.close()

        unread = client.post(f"/api/messages/{message_id}/read-state", json={"is_read": False})
        assert unread.status_code == 200
        assert unread.json()["is_read"] is False

        read = client.post(f"/api/messages/{message_id}/read-state", json={"is_read": True})
        assert read.status_code == 200
        assert read.json()["is_read"] is True

        assert calls == [
            ("gmail", "gmail-read-state-message", False),
            ("gmail", "gmail-read-state-message", True),
        ]
        db = SessionLocal()
        try:
            saved = db.get(EmailMessage, message_id)
            assert saved is not None and saved.is_read is True
        finally:
            db.close()


def test_full_thread_endpoint_does_not_change_provider_read_state(monkeypatch):
    with TestClient(app) as client:
        login(client)
        db = SessionLocal()
        try:
            user = db.scalar(select(User).where(User.email == settings.bootstrap_email.lower()))
            account = EmailAccount(
                user_id=user.id, provider="gmail",
                email=f"thread-view-{uuid.uuid4().hex}@example.com",
                connection_status="connected",
            )
            db.add(account)
            db.commit()
            db.refresh(account)
            source = EmailMessage(
                user_id=user.id, account_id=account.id,
                provider_message_id="gmail-thread-view-source",
                thread_key="gmail-thread-view",
                sender="supplier@example.com", recipients=account.email,
                subject="Complete trail test", body_text="Current source message",
                is_read=False,
            )
            db.add(source)
            db.commit()
            db.refresh(source)
            message_id = source.id
        finally:
            db.close()

        def fake_load(db_arg, account_arg, source_arg):
            assert account_arg.provider == "gmail"
            assert source_arg.id == message_id
            return [source_arg], True, [], 0

        monkeypatch.setattr(main_module, "load_provider_thread", fake_load)
        response = client.get(f"/api/messages/{message_id}/thread")
        assert response.status_code == 200
        assert response.json()["provider_scan_complete"] is True
        assert response.json()["read_state_changed"] is False
        assert response.json()["messages"][0]["body_text"] == "Current source message"

        db = SessionLocal()
        try:
            stored = db.get(EmailMessage, message_id)
            assert stored is not None and stored.is_read is False
        finally:
            db.close()


def test_new_outbound_draft_requires_explicit_from_account_and_final_approval(monkeypatch):
    with TestClient(app) as client:
        login(client)
        db = SessionLocal()
        try:
            user = db.scalar(select(User).where(User.email == settings.bootstrap_email.lower()))
            first = EmailAccount(
                user_id=user.id, provider="icloud",
                email=f"from-one-{uuid.uuid4().hex}@example.com",
                connection_status="connected",
            )
            second = EmailAccount(
                user_id=user.id, provider="gmail",
                email=f"from-two-{uuid.uuid4().hex}@example.com",
                connection_status="connected",
            )
            db.add_all([first, second])
            db.commit()
            db.refresh(first)
            db.refresh(second)
            second_id = second.id
            second_email = second.email
        finally:
            db.close()

        missing_from = client.post("/api/outbound-drafts", json={
            "to": ["recipient@example.com"],
            "subject": "New proposal",
            "body": "Please review the attached proposal.",
        })
        assert missing_from.status_code == 422

        created = client.post("/api/outbound-drafts", json={
            "account_id": second_id,
            "to": ["recipient@example.com"],
            "cc": ["copy@example.com"],
            "bcc": [],
            "subject": "New proposal",
            "body": "Please review the proposal.",
        })
        assert created.status_code == 200
        draft = created.json()
        assert draft["from_account"] == second_email
        assert draft["account_id"] == second_id
        assert draft["status"] == "draft"

        denied = client.post(f"/api/outbound-drafts/{draft['id']}/send", json={
            "confirm_send": False,
            "expected_updated_at": draft["updated_at"],
        })
        assert denied.status_code == 400

        db = SessionLocal()
        try:
            saved = db.get(OutboundDraft, draft["id"])
            assert saved is not None and saved.status == "draft"
        finally:
            db.close()

        sent_calls = []

        def fake_send(db_arg, account_arg, to, cc, bcc, subject, body, source):
            sent_calls.append({
                "account": account_arg.email, "to": to, "cc": cc,
                "bcc": bcc, "subject": subject, "body": body, "source": source,
            })
            return "provider-accepted-new-message"

        monkeypatch.setattr(main_module, "send_gmail", fake_send)
        sent = client.post(f"/api/outbound-drafts/{draft['id']}/send", json={
            "confirm_send": True,
            "expected_updated_at": draft["updated_at"],
        })
        assert sent.status_code == 200
        assert sent.json()["provider_accepted"] is True
        assert sent.json()["delivery_confirmed"] is False
        assert sent_calls == [{
            "account": second_email,
            "to": ["recipient@example.com"],
            "cc": ["copy@example.com"],
            "bcc": [],
            "subject": "New proposal",
            "body": "Please review the proposal.",
            "source": None,
        }]

        retry = client.post(f"/api/outbound-drafts/{draft['id']}/send", json={
            "confirm_send": True,
            "expected_updated_at": draft["updated_at"],
        })
        assert retry.status_code == 409


def test_new_outbound_draft_rejects_unowned_or_disconnected_from_account():
    with TestClient(app) as client:
        login(client)
        db = SessionLocal()
        try:
            user = db.scalar(select(User).where(User.email == settings.bootstrap_email.lower()))
            account = EmailAccount(
                user_id=user.id, provider="icloud",
                email=f"disconnected-{uuid.uuid4().hex}@example.com",
                connection_status="disconnected",
            )
            db.add(account)
            db.commit()
            db.refresh(account)
            disconnected_id = account.id
        finally:
            db.close()

        disconnected = client.post("/api/outbound-drafts", json={
            "account_id": disconnected_id,
            "to": ["recipient@example.com"],
            "subject": "Test",
            "body": "Test body",
        })
        assert disconnected.status_code == 409

        unowned = client.post("/api/outbound-drafts", json={
            "account_id": 99999999,
            "to": ["recipient@example.com"],
            "subject": "Test",
            "body": "Test body",
        })
        assert unowned.status_code == 409


def test_manual_sync_triggers_cloud_worker_after_durable_job_commit(monkeypatch):
    worker_calls = []
    monkeypatch.setattr(
        main_module, "trigger_mailbox_worker",
        lambda: worker_calls.append("triggered") or True,
    )
    with TestClient(app) as client:
        login(client)
        db = SessionLocal()
        try:
            user = db.scalar(select(User).where(User.email == settings.bootstrap_email.lower()))
            account = EmailAccount(
                user_id=user.id, provider="icloud",
                email=f"instant-sync-{uuid.uuid4().hex}@example.com",
                connection_status="connected",
            )
            db.add(account)
            db.commit()
            db.refresh(account)
            account_id = account.id
        finally:
            db.close()

        response = client.post(f"/api/sync/{account_id}")
        assert response.status_code == 200
        assert response.json() == {"queued": True, "worker_triggered": True}
        assert worker_calls == ["triggered"]

        db = SessionLocal()
        try:
            queued = db.scalars(select(SyncJob).where(
                SyncJob.account_id == account_id,
                SyncJob.status == "queued",
            )).all()
            assert len(queued) == 1
            assert queued[0].details == "Manual sync"
        finally:
            db.close()


def test_manual_sync_keeps_queued_job_when_cloud_trigger_is_not_configured(monkeypatch):
    monkeypatch.setattr(main_module, "trigger_mailbox_worker", lambda: False)
    with TestClient(app) as client:
        login(client)
        db = SessionLocal()
        try:
            user = db.scalar(select(User).where(User.email == settings.bootstrap_email.lower()))
            account = EmailAccount(
                user_id=user.id, provider="icloud",
                email=f"queued-sync-{uuid.uuid4().hex}@example.com",
                connection_status="connected",
            )
            db.add(account)
            db.commit()
            db.refresh(account)
            account_id = account.id
        finally:
            db.close()

        response = client.post(f"/api/sync/{account_id}")
        assert response.status_code == 200
        assert response.json() == {"queued": True, "worker_triggered": False}

        db = SessionLocal()
        try:
            queued = db.scalars(select(SyncJob).where(
                SyncJob.account_id == account_id,
                SyncJob.status == "queued",
            )).all()
            assert len(queued) == 1
        finally:
            db.close()


def test_login_throttle_blocks_after_five_failures_and_resets_after_window():
    from app.models import LoginThrottle
    from app.main import _login_identifier_hash
    from app.security import hash_password

    email = f"rate-limit-{uuid.uuid4().hex}@example.com"
    password = "known-user-test-password-123"
    db = SessionLocal()
    try:
        db.add(User(email=email, password_hash=hash_password(password)))
        db.commit()
    finally:
        db.close()
    identifier_hash = _login_identifier_hash(email)

    with TestClient(app) as client:
        for attempt in range(4):
            failed = client.post("/api/auth/login", json={
                "email": email, "password": "not-the-correct-password",
            })
            assert failed.status_code == 401

        # The fifth failed attempt activates the lockout.
        blocked = client.post("/api/auth/login", json={
            "email": email, "password": "not-the-correct-password",
        })
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) > 0

        db = SessionLocal()
        try:
            throttle = db.scalar(select(LoginThrottle).where(
                LoginThrottle.identifier_hash == identifier_hash
            ))
            assert throttle is not None
            throttle.window_started_at = datetime.now(timezone.utc) - timedelta(minutes=16)
            throttle.blocked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        finally:
            db.close()

        reset_window = client.post("/api/auth/login", json={
            "email": email, "password": "not-the-correct-password",
        })
        assert reset_window.status_code == 401

        db = SessionLocal()
        try:
            throttle = db.scalar(select(LoginThrottle).where(
                LoginThrottle.identifier_hash == identifier_hash
            ))
            assert throttle is not None and throttle.failed_attempts == 1
        finally:
            db.close()


def test_successful_login_clears_failed_login_counter():
    from app.models import LoginThrottle
    from app.main import _login_identifier_hash
    from app.security import hash_password

    email = f"clear-throttle-{uuid.uuid4().hex}@example.com"
    password = "another-known-test-password-456"
    db = SessionLocal()
    try:
        db.add(User(email=email, password_hash=hash_password(password)))
        db.commit()
    finally:
        db.close()
    identifier_hash = _login_identifier_hash(email)

    with TestClient(app) as client:
        failed = client.post("/api/auth/login", json={
            "email": email, "password": "wrong-password",
        })
        assert failed.status_code == 401

        successful = client.post("/api/auth/login", json={
            "email": email, "password": password,
        })
        assert successful.status_code == 200

        db = SessionLocal()
        try:
            throttle = db.scalar(select(LoginThrottle).where(
                LoginThrottle.identifier_hash == identifier_hash
            ))
            assert throttle is None
        finally:
            db.close()


def test_origin_guard_rejects_missing_and_cross_origin_production_mutations(monkeypatch):
    with TestClient(app) as client:
        monkeypatch.setattr(main_module.settings, "app_env", "production")
        monkeypatch.setattr(main_module.settings, "frontend_origin", "https://email.example.com")

        missing = client.post("/api/auth/logout")
        assert missing.status_code == 403

        foreign = client.post(
            "/api/auth/logout",
            headers={"Origin": "https://attacker.example"},
        )
        assert foreign.status_code == 403

        same_origin = client.post(
            "/api/auth/logout",
            headers={"Origin": "https://email.example.com"},
        )
        assert same_origin.status_code == 200

        # Enrolled Apple Shortcuts use device tokens rather than browser cookies.
        device_request = client.post("/api/apple/device/commands/poll")
        assert device_request.status_code == 401
