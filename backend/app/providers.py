import base64
import email
import imaplib
import re
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from email.message import EmailMessage as MIMEEmailMessage
from email.utils import make_msgid
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import EmailAccount, EmailMessage as StoredMessage
from .security import get_fernet

def decode_mime(value: str | None) -> str:
    if not value:
        return ""
    output = []
    for part, charset in decode_header(value):
        output.append(part.decode(charset or "utf-8", errors="replace") if isinstance(part, bytes) else part)
    return "".join(output)

def _decoded_body_parts(message):
    parts = message.walk() if message.is_multipart() else [message]
    plain, html = [], []
    for part in parts:
        if part.get_content_maintype() == "multipart" or part.get_content_disposition() == "attachment":
            continue
        if part.get_content_type() not in {"text/plain", "text/html"}:
            continue
        data = part.get_payload(decode=True) or b""
        text = data.decode(part.get_content_charset() or "utf-8", errors="replace")
        if part.get_content_type() == "text/plain":
            plain.append(text)
        else:
            html.append(text)
    return "\n".join(plain).strip(), "\n".join(html).strip()


def _html_body(message) -> str:
    from .email_html import sanitize_email_html
    _, html = _decoded_body_parts(message)
    return sanitize_email_html(html)[:500000]


def _plain_body(message) -> str:
    from .email_html import html_to_text
    plain, html = _decoded_body_parts(message)
    return (plain or html_to_text(html)).strip()[:200000]


def _connect(account: EmailAccount):
    if not account.encrypted_secret:
        raise RuntimeError("The iCloud app-specific password is unavailable. Reconnect this account.")
    password = get_fernet().decrypt(account.encrypted_secret.encode()).decode()
    client = imaplib.IMAP4_SSL("imap.mail.me.com", 993, timeout=30)
    client.login(account.email, password)
    return client, password

def sync_icloud(db: Session, account: EmailAccount) -> int:
    from .config import settings
    client, _ = _connect(account)
    try:
        status, _ = client.select("INBOX", readonly=True)
        if status != "OK":
            raise RuntimeError("iCloud Inbox could not be opened.")
        uidvalidity = _read_icloud_uidvalidity(client)
        if (account.icloud_sync_uidvalidity and uidvalidity
                and account.icloud_sync_uidvalidity != uidvalidity):
            # UIDs can be reassigned after a mailbox reset. Restart any partial batch.
            account.icloud_sync_uid_cursor = None
        if uidvalidity:
            account.icloud_sync_uidvalidity = uidvalidity
        now = datetime.now(timezone.utc)
        if account.icloud_sync_since:
            since = account.icloud_sync_since
        elif account.last_sync_at:
            last = account.last_sync_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            since = (last - timedelta(days=1)).strftime("%d-%b-%Y")
        else:
            since = (now - timedelta(days=settings.initial_sync_days)).strftime("%d-%b-%Y")
        status, data = client.uid("SEARCH", None, "SINCE", since)
        if status != "OK":
            raise RuntimeError("iCloud Inbox search failed.")
        identifiers = (data[0] or b"").split()
        if account.icloud_sync_uid_cursor:
            cursor = int(account.icloud_sync_uid_cursor)
            identifiers = [uid for uid in identifiers if int(uid) > cursor]
        batch = identifiers[:settings.max_messages_per_sync]
        imported = 0
        for uid in batch:
            status, payload = client.uid("FETCH", uid, "(BODY.PEEK[] FLAGS)")
            if status != "OK" or not payload or not isinstance(payload[0], tuple):
                continue
            raw = payload[0][1]
            metadata = payload[0][0] if isinstance(payload[0][0], bytes) else str(payload[0][0]).encode()
            parsed = email.message_from_bytes(raw)
            message_id = (parsed.get("Message-ID") or "").strip()
            if not message_id:
                message_id = (f"icloud-uidv-{uidvalidity}-{uid.decode(errors='ignore')}"
                              if uidvalidity else "icloud-uid-unverified-" + uid.decode(errors="ignore"))
            existing = db.scalar(select(StoredMessage).where(
                StoredMessage.account_id == account.id,
                StoredMessage.provider_message_id == message_id
            ))
            if existing:
                # Backfill the original HTML alternative for messages imported
                # before rich email rendering was introduced.
                if not existing.body_html:
                    existing.body_html = _html_body(parsed)
                    if not existing.body_text:
                        existing.body_text = _plain_body(parsed)
                continue
            try:
                received = email.utils.parsedate_to_datetime(parsed.get("Date")) if parsed.get("Date") else now
                if received.tzinfo is None:
                    received = received.replace(tzinfo=timezone.utc)
            except Exception:
                received = now
            body = _plain_body(parsed)
            refs = parsed.get("References") or parsed.get("In-Reply-To") or message_id
            has_attachments = any(
                part.get_filename() or part.get_content_disposition() == "attachment"
                for part in (parsed.walk() if parsed.is_multipart() else [])
            )
            db.add(StoredMessage(
                user_id=account.user_id, account_id=account.id,
                provider_message_id=message_id, thread_key=str(refs)[:500],
                sender=decode_mime(parsed.get("From")),
                recipients=", ".join(v for v in [
                    decode_mime(parsed.get("To")), decode_mime(parsed.get("Cc"))
                ] if v),
                subject=decode_mime(parsed.get("Subject")), received_at=received,
                snippet=body[:240], body_text=body, body_html=_html_body(parsed), is_read=(b"\\Seen" in metadata),
                has_attachments=has_attachments
            ))
            imported += 1
        if len(identifiers) > len(batch) and batch:
            account.icloud_sync_uid_cursor = batch[-1].decode(errors="ignore")
            account.icloud_sync_since = since
        else:
            account.icloud_sync_uid_cursor = None
            account.icloud_sync_since = None
            account.last_sync_at = now
        account.connection_status = "connected"
        db.commit()
        return imported
    finally:
        try:
            client.logout()
        except Exception:
            pass

def _read_icloud_uidvalidity(client) -> str | None:
    """Read current mailbox UIDVALIDITY, needed to make stored UID actions safe."""
    try:
        response_code, values = client.response("UIDVALIDITY")
    except Exception:
        return None
    if response_code != "UIDVALIDITY" or not values:
        return None
    value = values[0]
    value = value.decode(errors="ignore") if isinstance(value, bytes) else str(value)
    return value if value.isdigit() else None


def _find_icloud_uid(client, message_id: str) -> bytes:
    if message_id.startswith("icloud-uidv-"):
        value = message_id.removeprefix("icloud-uidv-")
        try:
            expected_validity, uid = value.split("-", 1)
        except ValueError:
            raise RuntimeError("The stored iCloud UID identity is invalid.")
        current_validity = _read_icloud_uidvalidity(client)
        if not expected_validity.isdigit() or not uid.isdigit():
            raise RuntimeError("The stored iCloud UID identity is invalid.")
        if not current_validity or current_validity != expected_validity:
            raise RuntimeError("The iCloud mailbox identity changed. Sync the mailbox again before using this action.")
        return uid.encode()
    if message_id.startswith(("icloud-uid-", "icloud-uid-unverified-")):
        raise RuntimeError("This imported iCloud message has no verified UIDVALIDITY. Refresh the mailbox before using this action.")
    if message_id.startswith("icloud-seq-"):
        raise RuntimeError("This older imported message has no Message-ID for a safe provider action.")
    clean = message_id.replace('"', "")
    status, data = client.uid("SEARCH", None, "HEADER", "Message-ID", '"' + clean + '"')
    if status != "OK" or not data or not data[0]:
        raise RuntimeError("The original message could not be located in iCloud.")
    return data[0].split()[-1]

def set_icloud_read(account: EmailAccount, message_id: str, read: bool = True) -> bool:
    client, _ = _connect(account)
    try:
        status, _ = client.select("INBOX", readonly=False)
        if status != "OK":
            raise RuntimeError("iCloud Inbox could not be opened for updating.")
        uid = _find_icloud_uid(client, message_id)
        flag = chr(92) + "Seen"
        operation = "+FLAGS.SILENT" if read else "-FLAGS.SILENT"
        status, response = client.uid("STORE", uid, operation, "(" + flag + ")")
        if status != "OK":
            raise RuntimeError("iCloud did not accept the read-state update.")

        # iCloud may acknowledge STORE before the updated FLAGS are visible to
        # the next FETCH. Verify the UID explicitly and tolerate a short
        # propagation delay; parse both tuple and byte response forms.
        confirmed = None
        for attempt in range(3):
            fetch_status, rows = client.uid("FETCH", uid, "(FLAGS)")
            if fetch_status == "OK":
                payloads = []
                for row in rows or []:
                    if isinstance(row, tuple) and row:
                        payloads.append(row[0])
                    elif isinstance(row, bytes):
                        payloads.append(row)
                for payload in payloads:
                    lowered = payload.lower()
                    flags_start = lowered.find(b"flags (")
                    if flags_start < 0:
                        continue
                    flags_end = lowered.find(b")", flags_start)
                    if flags_end < 0:
                        continue
                    flags = lowered[flags_start:flags_end + 1]
                    confirmed = b"\\seen" in flags
                    break
                if confirmed is read:
                    return confirmed
            if attempt < 2:
                import time
                time.sleep(0.35)

        if confirmed is None:
            raise RuntimeError("iCloud accepted the change but did not return readable FLAGS for verification. Refresh the mailbox and check Apple Mail.")
        raise RuntimeError("iCloud returned a different read state than requested after accepting the update. Refresh the mailbox and retry.")
    finally:
        try:
            client.logout()
        except Exception:
            pass

def move_icloud_to_trash(account: EmailAccount, message_id: str) -> bool:
    client, _ = _connect(account)
    try:
        status, _ = client.select("INBOX", readonly=False)
        if status != "OK":
            raise RuntimeError("iCloud Inbox could not be opened.")
        uid = _find_icloud_uid(client, message_id)
        status, folders = client.list()
        if status != "OK":
            raise RuntimeError("Could not locate the iCloud Trash folder.")
        candidates = []
        for row in folders or []:
            value = row.decode(errors="replace") if isinstance(row, bytes) else str(row)
            names = re.findall(r'"([^"]+)"', value)
            if names and re.search(r"(trash|deleted)", names[-1], re.I):
                candidates.append(names[-1])
        if not candidates:
            raise RuntimeError("No iCloud Trash folder was found; nothing was deleted.")
        status, _ = client.uid("MOVE", uid, '"' + candidates[0].replace('"', "") + '"')
        if status != "OK":
            raise RuntimeError("This iCloud server did not confirm moving the email to Trash.")
        return True
    finally:
        try:
            client.logout()
        except Exception:
            pass

MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024


def _icloud_message_parts(account: EmailAccount, message_id: str):
    client, _ = _connect(account)
    try:
        status, _ = client.select("INBOX", readonly=True)
        if status != "OK":
            raise RuntimeError("iCloud Inbox could not be opened for attachment access.")
        uid = _find_icloud_uid(client, message_id)
        status, payload = client.uid("FETCH", uid, "(BODY.PEEK[])")
        if status != "OK" or not payload or not isinstance(payload[0], tuple):
            raise RuntimeError("The original iCloud message could not be fetched.")
        raw_message = payload[0][1]
        if len(raw_message) > 60 * 1024 * 1024:
            raise ValueError("The original email exceeds the 60 MB in-app attachment parsing limit.")
        parsed = email.message_from_bytes(raw_message)
        result = []
        parts = parsed.walk() if parsed.is_multipart() else [parsed]
        for part in parts:
            if part.get_content_maintype() == "multipart":
                continue
            disposition = (part.get_content_disposition() or "").lower()
            raw_name = part.get_filename()
            content_id = (part.get("Content-ID") or "").strip("<>")
            if not raw_name and disposition != "attachment" and not content_id:
                continue
            filename = decode_mime(raw_name) if raw_name else (content_id or "attachment")
            data = part.get_payload(decode=True)
            if data is None and part.get_content_type() == "message/rfc822":
                data = part.as_bytes()
            data = data or b""
            result.append({
                "filename": filename[:255],
                "mime_type": part.get_content_type() or "application/octet-stream",
                "size": len(data),
                "is_inline": disposition == "inline" or bool(content_id),
                "data": data,
            })
        return result
    finally:
        try:
            client.logout()
        except Exception:
            pass


def list_icloud_attachments(account: EmailAccount, message_id: str) -> list[dict]:
    return [{
        "index": index,
        "filename": item["filename"],
        "mime_type": item["mime_type"],
        "size": item["size"],
        "is_inline": item["is_inline"],
        "can_preview": item["mime_type"] == "application/pdf" or item["mime_type"] in {"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"},
        "available": item["size"] <= MAX_ATTACHMENT_BYTES,
    } for index, item in enumerate(_icloud_message_parts(account, message_id))]


def get_icloud_attachment(account: EmailAccount, message_id: str, index: int) -> dict:
    items = _icloud_message_parts(account, message_id)
    if index < 0 or index >= len(items):
        raise LookupError("Attachment not found.")
    item = items[index]
    if item["size"] > MAX_ATTACHMENT_BYTES:
        raise ValueError("This attachment exceeds the 25 MB in-app download limit.")
    return item


def send_icloud_forward(
    account: EmailAccount, to: list[str], cc: list[str], bcc: list[str],
    subject: str, cover_note: str, source_message: StoredMessage,
    include_attachments: bool = True,
) -> str:
    if not account.encrypted_secret:
        raise RuntimeError("The iCloud app-specific password is unavailable. Reconnect this account.")
    password = get_fernet().decrypt(account.encrypted_secret.encode()).decode()
    forwarded = (
        "---------- Forwarded message ---------\n"
        f"From: {source_message.sender}\n"
        f"Date: {source_message.received_at or 'Unknown'}\n"
        f"Subject: {source_message.subject}\n"
        f"To: {source_message.recipients}\n\n"
        f"{source_message.body_text or ''}"
    )
    body = (cover_note.strip() + "\n\n" if cover_note.strip() else "") + forwarded
    message = MIMEEmailMessage()
    message["From"] = account.email
    message["To"] = ", ".join(to)
    if cc:
        message["Cc"] = ", ".join(cc)
    message["Subject"] = subject
    message["Message-ID"] = make_msgid()
    message.set_content(body)

    attachments = _icloud_message_parts(account, source_message.provider_message_id) if include_attachments else []
    total_size = 0
    for item in attachments:
        data = item["data"]
        total_size += len(data)
        if total_size > MAX_ATTACHMENT_BYTES:
            raise ValueError("The combined original attachments exceed the 25 MB forwarding limit.")
        mime_type = item["mime_type"].split("/", 1)
        if len(mime_type) != 2:
            mime_type = ["application", "octet-stream"]
        message.add_attachment(
            data,
            maintype=mime_type[0],
            subtype=mime_type[1],
            filename=item["filename"] or "attachment",
        )
    recipients = list(dict.fromkeys(to + cc + bcc))
    if not recipients:
        raise RuntimeError("No recipients were supplied.")
    with smtplib.SMTP("smtp.mail.me.com", 587, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(account.email, password)
        refused = smtp.send_message(message, from_addr=account.email, to_addrs=recipients)
        if refused:
            raise RuntimeError("The iCloud SMTP server refused one or more recipients.")
    return message["Message-ID"]


def send_icloud(account: EmailAccount, to: list[str], cc: list[str], bcc: list[str],
                subject: str, body: str, source_message: StoredMessage | None = None, attachments: list[dict] | None = None) -> str:
    if not account.encrypted_secret:
        raise RuntimeError("The iCloud app-specific password is unavailable. Reconnect this account.")
    password = get_fernet().decrypt(account.encrypted_secret.encode()).decode()
    message = MIMEEmailMessage()
    message["From"] = account.email
    message["To"] = ", ".join(to)
    if cc:
        message["Cc"] = ", ".join(cc)
    message["Subject"] = subject
    message["Message-ID"] = make_msgid()
    if source_message and not source_message.provider_message_id.startswith(("icloud-seq-", "icloud-uid")):
        message["In-Reply-To"] = source_message.provider_message_id
        message["References"] = (source_message.thread_key + " " + source_message.provider_message_id).strip()
    message.set_content(body)
    for item in attachments or []:
        raw = base64.b64decode(item.get("data_base64", ""), validate=True)
        mime = str(item.get("mime_type") or "application/octet-stream").split("/", 1)
        message.add_attachment(raw, maintype=mime[0], subtype=mime[1] if len(mime)>1 else "octet-stream", filename=str(item.get("filename") or "attachment"))
    recipients = list(dict.fromkeys(to + cc + bcc))
    if not recipients:
        raise RuntimeError("No recipients were supplied.")
    with smtplib.SMTP("smtp.mail.me.com", 587, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(account.email, password)
        refused = smtp.send_message(message, from_addr=account.email, to_addrs=recipients)
        if refused:
            raise RuntimeError("The iCloud SMTP server refused one or more recipients.")
    return message["Message-ID"]


def set_icloud_starred(account: EmailAccount, message_id: str, starred: bool = True) -> bool:
    """Set the IMAP \\Flagged flag on the source message."""
    client, _ = _connect(account)
    try:
        status, _ = client.select("INBOX", readonly=False)
        if status != "OK":
            raise RuntimeError("iCloud Inbox could not be opened for starring.")
        uid = _find_icloud_uid(client, message_id)
        flag = chr(92) + "Flagged"
        operation = "+FLAGS.SILENT" if starred else "-FLAGS.SILENT"
        status, _ = client.uid("STORE", uid, operation, "(" + flag + ")")
        if status != "OK":
            raise RuntimeError("iCloud did not accept the starred-state update.")
        status, rows = client.uid("FETCH", uid, "(FLAGS)")
        if status != "OK":
            raise RuntimeError("Could not verify the iCloud starred state.")
        for row in rows or []:
            payload = row[0] if isinstance(row, tuple) and row else row
            if not isinstance(payload, bytes):
                continue
            start = payload.lower().find(b"flags (")
            end = payload.find(b")", start)
            if start < 0 or end < 0:
                continue
            confirmed = b"\\flagged" in payload[start:end + 1].lower()
            if confirmed == starred:
                return True
            raise RuntimeError("iCloud returned a different starred state than requested.")
        raise RuntimeError("iCloud did not return FLAGS to verify starring.")
    finally:
        try:
            client.logout()
        except Exception:
            pass
