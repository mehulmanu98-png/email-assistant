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
