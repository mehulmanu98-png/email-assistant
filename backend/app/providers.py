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

def _plain_body(message) -> str:
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
    if plain:
        body = "\n".join(plain)
    else:
        body = "\n".join(html)
        body = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", body)
        body = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", body)
        body = re.sub(r"(?s)<[^>]+>", " ", body)
        body = body.replace("&nbsp;", " ").replace("&amp;", "&")
    return body.strip()[:200000]

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
            message_id = (parsed.get("Message-ID") or "").strip() or "icloud-uid-" + uid.decode(errors="ignore")
            if db.scalar(select(StoredMessage.id).where(
                StoredMessage.account_id == account.id,
                StoredMessage.provider_message_id == message_id
            )):
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
                snippet=body[:240], body_text=body, is_read=(b"\\Seen" in metadata),
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

def _find_icloud_uid(client, message_id: str) -> bytes:
    if message_id.startswith("icloud-uid-"):
        uid = message_id.removeprefix("icloud-uid-")
        if uid.isdigit():
            return uid.encode()
        raise RuntimeError("The stored iCloud UID is invalid.")
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
        status, _ = client.uid("STORE", uid, operation, "(" + flag + ")")
        if status != "OK":
            raise RuntimeError("iCloud did not confirm the read-state update.")
        status, rows = client.uid("FETCH", uid, "(FLAGS)")
        if status != "OK":
            raise RuntimeError("Could not verify the iCloud read state.")
        confirmed = any(isinstance(row, tuple) and flag.encode() in row[0] for row in rows)
        if confirmed != read:
            raise RuntimeError("iCloud returned a different read state than requested.")
        return confirmed
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

def send_icloud(account: EmailAccount, to: list[str], cc: list[str], bcc: list[str],
                subject: str, body: str, source_message: StoredMessage | None = None) -> str:
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
    if source_message and not source_message.provider_message_id.startswith(("icloud-seq-", "icloud-uid-")):
        message["In-Reply-To"] = source_message.provider_message_id
        message["References"] = (source_message.thread_key + " " + source_message.provider_message_id).strip()
    message.set_content(body)
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
