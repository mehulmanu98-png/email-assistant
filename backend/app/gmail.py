import base64
import re
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage as MIMEEmailMessage
from email.utils import make_msgid
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import EmailAccount, EmailMessage as StoredMessage
from .security import get_fernet

TOKEN_URL = "https://oauth2.googleapis.com/token"
API_ROOT = "https://gmail.googleapis.com/gmail/v1/users/me"

def _decode(data: str | None) -> str:
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")
    except Exception:
        return ""

def _clean_html(value: str) -> str:
    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def _walk_parts(part: dict, texts: list[str], attachment_flag: list[bool]):
    filename = part.get("filename")
    if filename:
        attachment_flag[0] = True
    mime = part.get("mimeType", "")
    body = part.get("body") or {}
    if mime == "text/plain" and body.get("data"):
        texts.append(_decode(body["data"]))
    elif mime == "text/html" and body.get("data") and not texts:
        texts.append(_clean_html(_decode(body["data"])))
    for child in part.get("parts") or []:
        _walk_parts(child, texts, attachment_flag)

def parse_gmail_message(payload: dict) -> dict:
    headers = {str(h.get("name", "")).lower(): str(h.get("value", "")) for h in payload.get("headers", [])}
    texts: list[str] = []
    has_attachments = [False]
    _walk_parts(payload, texts, has_attachments)
    body = "\n".join(t for t in texts if t).strip()[:200000]
    return {
        "sender": headers.get("from", ""),
        "recipients": ", ".join(x for x in [headers.get("to", ""), headers.get("cc", "")] if x),
        "subject": headers.get("subject", ""),
        "message_id": headers.get("message-id", ""),
        "references": headers.get("references", ""),
        "body": body,
        "has_attachments": has_attachments[0],
    }

def _tokens(account: EmailAccount) -> dict:
    if not account.encrypted_secret:
        raise RuntimeError("Gmail credentials are unavailable. Reconnect this account.")
    import json
    try:
        return json.loads(get_fernet().decrypt(account.encrypted_secret.encode()).decode())
    except Exception as exc:
        raise RuntimeError("Stored Gmail credentials could not be decrypted; reconnect the account.") from exc

def _save_tokens(account: EmailAccount, tokens: dict):
    import json
    account.encrypted_secret = get_fernet().encrypt(json.dumps(tokens).encode()).decode()

def _access_token(account: EmailAccount) -> str:
    tokens = _tokens(account)
    expires_at = datetime.fromtimestamp(float(tokens.get("expires_at", 0)), timezone.utc)
    if tokens.get("access_token") and expires_at > datetime.now(timezone.utc) + timedelta(seconds=90):
        return tokens["access_token"]
    refresh = tokens.get("refresh_token")
    if not refresh:
        raise RuntimeError("Google did not issue a refresh token. Reconnect Gmail with offline access.")
    # Refresh is performed by the caller's database-backed service route.
    raise RuntimeError("Gmail token refresh requires a database session.")

def refresh_gmail_access(db: Session, account: EmailAccount) -> str:
    tokens = _tokens(account)
    expires_at = datetime.fromtimestamp(float(tokens.get("expires_at", 0)), timezone.utc)
    if tokens.get("access_token") and expires_at > datetime.now(timezone.utc) + timedelta(seconds=90):
        return tokens["access_token"]
    refresh = tokens.get("refresh_token")
    if not refresh:
        raise RuntimeError("Google did not issue a refresh token. Reconnect Gmail with offline access.")
    from .config import settings
    if not settings.google_client_id or not settings.google_client_secret:
        raise RuntimeError("Google OAuth credentials are not configured on the server.")
    response = httpx.post(TOKEN_URL, data={
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "refresh_token": refresh,
        "grant_type": "refresh_token",
    }, timeout=30)
    if response.status_code != 200:
        raise RuntimeError("Google rejected the refresh token. Reconnect this Gmail account.")
    updated = response.json()
    tokens["access_token"] = updated["access_token"]
    tokens["expires_at"] = datetime.now(timezone.utc).timestamp() + int(updated.get("expires_in", 3600))
    _save_tokens(account, tokens)
    db.commit()
    return tokens["access_token"]

def gmail_request(db: Session, account: EmailAccount, method: str, path: str,
                  params: dict | None = None, json_body: dict | None = None) -> dict:
    token = refresh_gmail_access(db, account)
    response = httpx.request(method, API_ROOT + path,
        headers={"Authorization": "Bearer " + token},
        params=params, json=json_body, timeout=45)
    if response.status_code >= 400:
        # Deliberately do not return provider response bodies; they may contain private data.
        raise RuntimeError(f"Gmail API request failed with HTTP {response.status_code}.")
    return response.json() if response.content else {}

def sync_gmail(db: Session, account: EmailAccount, limit: int = 500) -> int:
    if account.last_sync_at:
        after = int(account.last_sync_at.timestamp()) - 60
        query = f"in:inbox after:{after}"
    else:
        query = "in:inbox newer_than:90d"
    page_token = None
    message_ids = []
    while len(message_ids) < limit:
        params = {"q": query, "maxResults": min(100, limit - len(message_ids))}
        if page_token:
            params["pageToken"] = page_token
        data = gmail_request(db, account, "GET", "/messages", params=params)
        message_ids.extend(item["id"] for item in data.get("messages", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    imported = 0
    for provider_id in message_ids:
        if db.scalar(select(StoredMessage.id).where(
            StoredMessage.account_id == account.id,
            StoredMessage.provider_message_id == provider_id
        )):
            continue
        data = gmail_request(db, account, "GET", "/messages/" + provider_id, params={"format": "full"})
        parsed = parse_gmail_message(data.get("payload") or {})
        try:
            received = datetime.fromtimestamp(int(data.get("internalDate", "0")) / 1000, timezone.utc)
        except Exception:
            received = datetime.now(timezone.utc)
        db.add(StoredMessage(
            user_id=account.user_id, account_id=account.id,
            provider_message_id=provider_id, thread_key=str(data.get("threadId", provider_id)),
            sender=parsed["sender"], recipients=parsed["recipients"], subject=parsed["subject"],
            received_at=received, snippet=(data.get("snippet") or parsed["body"][:240])[:500],
            body_text=parsed["body"], is_read=("UNREAD" not in data.get("labelIds", [])),
            has_attachments=parsed["has_attachments"]
        ))
        imported += 1
    account.last_sync_at = datetime.now(timezone.utc)
    account.connection_status = "connected"
    db.commit()
    return imported

def set_gmail_read(db: Session, account: EmailAccount, provider_id: str, read: bool = True) -> bool:
    if read:
        result = gmail_request(db, account, "POST", "/messages/" + provider_id + "/modify",
                               json_body={"removeLabelIds": ["UNREAD"]})
    else:
        result = gmail_request(db, account, "POST", "/messages/" + provider_id + "/modify",
                               json_body={"addLabelIds": ["UNREAD"]})
    return ("UNREAD" not in result.get("labelIds", [])) == read

def trash_gmail(db: Session, account: EmailAccount, provider_id: str) -> bool:
    data = gmail_request(db, account, "POST", "/messages/" + provider_id + "/trash")
    return bool(data.get("id") == provider_id)

def send_gmail(db: Session, account: EmailAccount, to: list[str], cc: list[str], bcc: list[str],
               subject: str, body: str, source_message: StoredMessage | None = None) -> str:
    message = MIMEEmailMessage()
    message["From"] = account.email
    message["To"] = ", ".join(to)
    if cc:
        message["Cc"] = ", ".join(cc)
    message["Subject"] = subject
    if bcc:
        message["Bcc"] = ", ".join(bcc)
    message["Message-ID"] = make_msgid()
    thread_id = None
    if source_message:
        thread_id = source_message.thread_key
        original = gmail_request(db, account, "GET", "/messages/" + source_message.provider_message_id,
                                 params={"format": "metadata", "metadataHeaders": ["Message-ID", "References"]})
        headers = {str(h.get("name", "")).lower(): str(h.get("value", "")) for h in (original.get("payload") or {}).get("headers", [])}
        if headers.get("message-id"):
            message["In-Reply-To"] = headers["message-id"]
            message["References"] = (headers.get("references", "") + " " + headers["message-id"]).strip()
    message.set_content(body)
    recipients = list(dict.fromkeys(to + cc + bcc))
    if not recipients:
        raise RuntimeError("No recipients were supplied.")
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode().rstrip("=")
    request_body = {"raw": raw}
    if thread_id:
        request_body["threadId"] = thread_id
    result = gmail_request(db, account, "POST", "/messages/send", json_body=request_body)
    if not result.get("id"):
        raise RuntimeError("Gmail did not confirm an accepted message.")
    return str(result["id"])
