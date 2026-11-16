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
