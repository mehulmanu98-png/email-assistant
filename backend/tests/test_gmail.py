import base64
from app.gmail import parse_gmail_message

def encoded(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")

def test_parse_simple_gmail_plain_text_message():
    payload = {
        "mimeType": "text/plain",
        "headers": [
            {"name": "From", "value": "Sender <sender@example.com>"},
            {"name": "To", "value": "owner@example.com"},
            {"name": "Subject", "value": "Test subject"},
            {"name": "Message-ID", "value": "<m1@example.com>"}
        ],
        "body": {"data": encoded("Hello from Gmail")}
    }
    result = parse_gmail_message(payload)
    assert result["sender"] == "Sender <sender@example.com>"
    assert result["subject"] == "Test subject"
    assert result["body"] == "Hello from Gmail"
    assert result["has_attachments"] is False

def test_parse_nested_gmail_message_and_detect_attachment():
    payload = {
        "mimeType": "multipart/mixed",
        "headers": [],
        "parts": [
            {"mimeType": "text/plain", "body": {"data": encoded("Plain body")}},
            {"mimeType": "application/pdf", "filename": "invoice.pdf", "body": {"attachmentId": "att-1"}}
        ]
    }
    result = parse_gmail_message(payload)
    assert result["body"] == "Plain body"
    assert result["has_attachments"] is True


def test_gmail_attachment_metadata_and_inline_content_are_detected():
    from app.gmail import _gmail_attachment_parts, _decode_bytes
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "application/pdf",
                "filename": "invoice.pdf",
                "headers": [{"name": "Content-Disposition", "value": "attachment; filename=invoice.pdf"}],
                "body": {"attachmentId": "attachment-1", "size": 1234},
            },
            {
                "mimeType": "image/png",
                "headers": [{"name": "Content-ID", "value": "<logo@example.com>"}],
                "body": {"data": encoded("image-bytes"), "size": 11},
            },
        ],
    }
    parts = _gmail_attachment_parts(payload)
    assert len(parts) == 2
    assert parts[0]["filename"] == "invoice.pdf"
    assert parts[0]["attachment_id"] == "attachment-1"
    assert parts[0]["is_inline"] is False
    assert parts[1]["filename"] == "logo@example.com"
    assert parts[1]["is_inline"] is True
    assert _decode_bytes(parts[1]["data"]) == b"image-bytes"


def test_gmail_forward_builds_new_message_without_original_thread_id(monkeypatch):
    from email import message_from_bytes
    from app import gmail
    from app.models import EmailAccount, EmailMessage as StoredMessage
    captured = {}

    def fake_gmail_request(db, account, method, path, json_body=None, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["json_body"] = json_body
        return {"id": "gmail-forward-result"}

    monkeypatch.setattr(gmail, "gmail_request", fake_gmail_request)
    monkeypatch.setattr(gmail, "list_gmail_attachments", lambda *args: [{
        "index": 0, "filename": "contract.pdf", "mime_type": "application/pdf",
        "size": 8, "is_inline": False, "can_preview": True, "available": True,
    }])
    monkeypatch.setattr(gmail, "get_gmail_attachment", lambda *args: {
        "filename": "contract.pdf", "mime_type": "application/pdf",
        "size": 8, "is_inline": False, "data": b"%PDFtest",
    })
    account = EmailAccount(
        id=1, user_id=1, provider="gmail",
        email="owner@example.com", connection_status="connected",
    )
    source = StoredMessage(
        id=9, user_id=1, account_id=1,
        provider_message_id="original-provider-id",
        thread_key="original-gmail-thread",
        sender="sender@example.com", recipients="owner@example.com",
        subject="Contract", body_text="Original contract text",
    )

    result = gmail.send_gmail_forward(
        None, account, ["recipient@example.com"], [], [],
        "Fwd: Contract", "Please review.", source, True,
    )

    assert result == "gmail-forward-result"
    assert captured["method"] == "POST"
    assert captured["path"] == "/messages/send"
    assert "threadId" not in captured["json_body"]
    raw = captured["json_body"]["raw"]
    parsed = message_from_bytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    assert parsed["In-Reply-To"] is None
    assert parsed["From"] == "owner@example.com"
    assert parsed["To"] == "recipient@example.com"
    parts = list(parsed.walk())
    assert any(part.get_filename() == "contract.pdf" for part in parts)
    body = next(part for part in parts if part.get_content_type() == "text/plain")
    body_text = body.get_payload(decode=True).decode(body.get_content_charset() or "utf-8")
    assert "Original contract text" in body_text
    assert "Please review." in body_text
