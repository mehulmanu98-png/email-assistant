from app.email_html import html_to_text, sanitize_email_html
from app.gmail import parse_gmail_message
import base64


def encoded(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def test_email_html_keeps_formatting_but_removes_active_content():
    source = (
        '<div style="color:#222;font-size:16px" onclick="alert(1)">'
        '<p>Hello <b>Mehul</b></p>'
        '<a href="https://example.com" onmouseover="alert(1)">Open</a>'
        '<img src="https://example.com/logo.png" onerror="alert(1)" alt="Logo">'
        '<script>alert("bad")</script>'
        '<iframe src="https://evil.example"></iframe>'
        '<a href="javascript:alert(1)">Unsafe</a>'
        '</div>'
    )
    safe = sanitize_email_html(source)
    assert "<b>Mehul</b>" in safe
    assert 'href="https://example.com"' in safe
    assert 'src="https://example.com/logo.png"' in safe
    assert "onclick=" not in safe
    assert "onmouseover=" not in safe
    assert "onerror=" not in safe
    assert "javascript:" not in safe
    assert "<script" not in safe
    assert "<iframe" not in safe


def test_html_to_text_extracts_readable_fallback():
    assert html_to_text("<p>Hello <b>Mehul</b></p><p>Second line</p>") == "Hello Mehul\nSecond line"


def test_gmail_parser_retains_html_alongside_plain_text():
    payload = {
        "mimeType": "multipart/alternative",
        "headers": [{"name": "From", "value": "sender@example.com"}],
        "parts": [
            {"mimeType": "text/plain", "body": {"data": encoded("Hello in plain text")}},
            {"mimeType": "text/html", "body": {"data": encoded('<div><p>Hello <b>Mehul</b></p><img src="https://example.com/logo.png"></div>')}},
        ],
    }
    result = parse_gmail_message(payload)
    assert result["body"] == "Hello in plain text"
    assert "<b>Mehul</b>" in result["body_html"]
    assert "https://example.com/logo.png" in result["body_html"]
