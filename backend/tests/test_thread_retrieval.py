import base64
from datetime import timezone
from email.message import EmailMessage as MIMEMessage

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import User, EmailAccount, EmailMessage
from app.thread_retrieval import load_provider_thread


def _memory_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _gmail_message(provider_id, thread_id, sender, subject, body, timestamp, labels):
    encoded = base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
    return {
        "id": provider_id,
        "threadId": thread_id,
        "internalDate": str(timestamp),
        "snippet": body[:120],
        "labelIds": labels,
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": sender},
                {"name": "To", "value": "owner@example.com"},
                {"name": "Subject", "value": subject},
                {"name": "Message-ID", "value": f"<{provider_id}@example.com>"},
            ],
            "body": {"data": encoded},
        },
    }


def test_gmail_thread_retrieval_imports_older_sent_message_and_refreshes_provider_state(monkeypatch):
    from app import gmail

    db = _memory_session()
    try:
        user = User(email="thread-owner@example.com", password_hash="unused")
        db.add(user)
        db.flush()
        account = EmailAccount(
            user_id=user.id, provider="gmail", email="owner@example.com",
            connection_status="connected", encrypted_secret="unused",
        )
        db.add(account)
        db.flush()
        source = EmailMessage(
            user_id=user.id, account_id=account.id,
            provider_message_id="gmail-new-reply", thread_key="gmail-thread-42",
            sender="supplier@example.com", recipients=account.email,
            subject="Re: Quotation", body_text="Cached latest reply",
            is_read=False,
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        provider_messages = [
            _gmail_message(
                "gmail-original", "gmail-thread-42", "owner@example.com",
                "Initial enquiry", "Our original requirements", 1_700_000_000_000,
                ["SENT"],
            ),
            _gmail_message(
                "gmail-new-reply", "gmail-thread-42", "supplier@example.com",
                "Re: Quotation", "Updated supplier response", 1_700_000_100_000,
                ["INBOX", "UNREAD"],
            ),
        ]
        calls = []

        def fake_request(db_arg, account_arg, method, path, params=None, **kwargs):
            calls.append((method, path, params))
            return {"id": "gmail-thread-42", "messages": provider_messages}

        monkeypatch.setattr(gmail, "gmail_request", fake_request)
        rows, complete, reasons, imported = load_provider_thread(db, account, source)

        assert calls == [("GET", "/threads/gmail-thread-42", {"format": "full"})]
        assert complete is True
        assert reasons == []
        assert imported == 1
        assert [row.provider_message_id for row in rows] == ["gmail-original", "gmail-new-reply"]
        assert rows[0].body_text == "Our original requirements"
        assert rows[0].is_read is True
        assert rows[1].body_text == "Updated supplier response"
        assert rows[1].is_read is False
    finally:
        db.close()


class FakeThreadIMAP:
    def __init__(self, original_raw, reply_raw):
        self.current_mailbox = ""
        self.raw_by_uid = {"9": original_raw, "1": reply_raw}
        self.operations = []

    def list(self):
        return "OK", [
            b'(\\HasNoChildren) "/" "INBOX"',
            b'(\\HasNoChildren) "/" "Sent Messages"',
            b'(\\HasNoChildren) "/" "Deleted Messages"',
        ]

    def select(self, mailbox, readonly=True):
        self.current_mailbox = str(mailbox).strip('"')
        self.operations.append(("SELECT", self.current_mailbox, readonly))
        return "OK", [b"1"]

    def uid(self, *args):
        command = str(args[0]).upper()
        self.operations.append((command, *args[1:]))
        if command == "SEARCH":
            header = str(args[3])
            query = str(args[4]).strip('"')
            root = "<original@example.com>"
            if self.current_mailbox == "INBOX" and header == "In-Reply-To" and query == root:
                return "OK", [b"1"]
            if self.current_mailbox == "Sent Messages" and header == "Message-ID" and query == root:
                return "OK", [b"9"]
            return "OK", [b""]
        if command == "FETCH":
            uid = args[1].decode() if isinstance(args[1], bytes) else str(args[1])
            flags = b"(FLAGS (\\Seen))" if uid == "9" else b"(FLAGS ())"
            return "OK", [(flags, self.raw_by_uid[uid])]
        if command == "STORE":
            raise AssertionError("Thread retrieval must not change mailbox read flags.")
        raise AssertionError(f"Unexpected IMAP operation: {command}")

    def logout(self):
        return "BYE"


def _raw_email(sender, subject, message_id, body, date, in_reply_to=None):
    message = MIMEMessage()
    message["From"] = sender
    message["To"] = "owner@example.com"
    message["Subject"] = subject
    message["Message-ID"] = message_id
    message["Date"] = date
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
    message.set_content(body)
    return message.as_bytes()


def test_icloud_thread_searches_inbox_and_sent_without_marking_messages_read(monkeypatch):
    from app import providers

    db = _memory_session()
    try:
        user = User(email="icloud-owner@example.com", password_hash="unused")
        db.add(user)
        db.flush()
        account = EmailAccount(
            user_id=user.id, provider="icloud", email="owner@example.com",
            connection_status="connected", encrypted_secret="unused",
        )
        db.add(account)
        db.flush()
        source = EmailMessage(
            user_id=user.id, account_id=account.id,
            provider_message_id="<reply@example.com>",
            thread_key="<original@example.com>",
            sender="supplier@example.com", recipients=account.email,
            subject="Re: Initial enquiry", body_text="Cached reply",
            is_read=False,
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        original = _raw_email(
            "owner@example.com", "Initial enquiry", "<original@example.com>",
            "Original requirements from the owner", "Tue, 14 Nov 2023 10:00:00 +0000",
        )
        reply = _raw_email(
            "supplier@example.com", "Re: Initial enquiry", "<reply@example.com>",
            "Supplier reply", "Tue, 14 Nov 2023 11:00:00 +0000",
            "<original@example.com>",
        )
        client = FakeThreadIMAP(original, reply)
        monkeypatch.setattr(providers, "_connect", lambda account_arg: (client, "unused"))

        rows, complete, reasons, imported = load_provider_thread(db, account, source)

        assert complete is True
        assert reasons == []
        assert imported == 1
        assert [row.provider_message_id for row in rows] == [
            "<original@example.com>", "<reply@example.com>"
        ]
        assert rows[0].body_text == "Original requirements from the owner"
        assert rows[0].is_read is True
        assert rows[1].body_text == "Supplier reply"
        assert rows[1].is_read is False
        assert all(op[0] != "STORE" for op in client.operations)
        assert ("SELECT", "INBOX", True) in client.operations
        assert ("SELECT", "Sent Messages", True) in client.operations
    finally:
        db.close()
