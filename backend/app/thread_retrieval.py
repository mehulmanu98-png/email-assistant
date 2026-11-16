"""On-demand source-provider retrieval for complete email threads.

Thread loading uses read-only provider operations. It may import older messages
into the app cache, but it never changes a mailbox read flag.
"""
import email
import email.utils
import re
from datetime import timezone
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import EmailAccount, EmailMessage
from .conversation_sync import canonical_thread_key, _thread_messages
from . import gmail, providers

MAX_THREAD_MESSAGES = 200
MAX_THREAD_SEEDS = 100
SKIP_ICLOUD_FOLDERS = re.compile(r"(?:trash|deleted|junk|spam|draft)", re.I)


def _message_ids(value: str | None) -> list[str]:
    if not value:
        return []
    found = re.findall(r"<[^<>\r\n]+>", value)
    if found:
        return list(dict.fromkeys(found))
    return [part for part in value.split() if part and not any(ch in part for ch in "\r\n\x00")]


def _received_at(value: str | None):
    if not value:
        return None
    try:
        result = email.utils.parsedate_to_datetime(value)
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return result
    except Exception:
        return None


def _gmail_thread(db: Session, account: EmailAccount, source: EmailMessage):
    thread_id = str(source.thread_key or source.provider_message_id).strip()
    if not thread_id:
        raise RuntimeError("This Gmail message has no usable thread identity.")

    result = gmail.gmail_request(
        db, account, "GET", "/threads/" + quote(thread_id, safe=""),
        params={"format": "full"},
    )
    provider_messages = result.get("messages") or []
    if not isinstance(provider_messages, list) or not provider_messages:
        raise RuntimeError("Gmail did not return messages for this thread.")

    imported = 0
    excluded = 0
    for item in provider_messages[:MAX_THREAD_MESSAGES]:
        provider_id = str(item.get("id") or "").strip()
        if not provider_id:
            excluded += 1
            continue
        labels = set(item.get("labelIds") or [])
        existing = db.scalar(select(EmailMessage).where(
            EmailMessage.account_id == account.id,
            EmailMessage.provider_message_id == provider_id,
        ))
        if "TRASH" in labels:
            if existing:
                existing.is_trashed = True
            excluded += 1
            continue

        parsed = gmail.parse_gmail_message(item.get("payload") or {})
        try:
            received = (
                __import__("datetime").datetime.fromtimestamp(
                    int(item.get("internalDate", "0")) / 1000, timezone.utc
                )
                if item.get("internalDate") else None
            )
        except Exception:
            received = None

        values = {
            "thread_key": str(item.get("threadId") or thread_id),
            "sender": parsed["sender"],
            "recipients": parsed["recipients"],
            "subject": parsed["subject"],
            "received_at": received,
            "snippet": str(item.get("snippet") or parsed["body"][:240])[:500],
            "body_text": parsed["body"],
            "is_read": "UNREAD" not in labels,
            "has_attachments": parsed["has_attachments"],
            "is_trashed": False,
        }
        if existing:
            for key, value in values.items():
                setattr(existing, key, value)
        else:
            db.add(EmailMessage(
                user_id=account.user_id,
                account_id=account.id,
                provider_message_id=provider_id,
                **values,
            ))
            imported += 1

    db.flush()
    rows = _thread_messages(db, account, thread_id)
    db.commit()
    reasons = []
    if len(provider_messages) > MAX_THREAD_MESSAGES:
        reasons.append(f"Gmail returned more than the {MAX_THREAD_MESSAGES}-message retrieval limit.")
    if excluded:
        reasons.append(f"{excluded} provider message(s) could not be included because they were in Trash or lacked an ID.")
    return rows, not reasons, reasons, imported


def _imap_mailbox_name(row) -> str | None:
    raw = row if isinstance(row, bytes) else str(row).encode()
    if b"\\Noselect" in raw:
        return None
    matches = re.findall(rb'"((?:[^"\\]|\\.)*)"', raw)
    if matches:
        value = matches[-1].replace(b'\\"', b'"').replace(b"\\\\", b"\\")
        return value.decode("utf-8", errors="replace")
    parts = raw.decode("utf-8", errors="replace").split()
    return parts[-1].strip('"') if parts else None


def _imap_quote(value: str) -> str:
    # Provider-supplied Message-IDs are search values, not IMAP commands.
    safe = value.replace("\\", "").replace('"', "").replace("\r", "").replace("\n", "")
    return '"' + safe + '"'


def _icloud_thread(db: Session, account: EmailAccount, source: EmailMessage):
    root_key = canonical_thread_key(db, account, source)
    existing_rows = _thread_messages(db, account, root_key)
    seeds: list[str] = []
    for value in [root_key, source.provider_message_id, *[row.provider_message_id for row in existing_rows]]:
        for message_id in _message_ids(value):
            if message_id not in seeds:
                seeds.append(message_id)
    if not seeds:
        reason = ["The available iCloud message has no RFC Message-ID, so a provider-wide thread search is not reliable."]
        db.commit()
        return existing_rows, False, reason, 0

    client, _ = providers._connect(account)
    imported = 0
    reasons: list[str] = []
    processed: set[tuple[str, str]] = set()
    root_ids = _message_ids(root_key)
    stable_root = root_ids[0] if root_ids else seeds[0]
    try:
        status, folder_rows = client.list()
        if status != "OK":
            raise RuntimeError("iCloud did not return the mailbox folder list.")
        folders = []
        for item in folder_rows or []:
            name = _imap_mailbox_name(item)
            if not name or SKIP_ICLOUD_FOLDERS.search(name):
                continue
            if name not in folders:
                folders.append(name)
        if not folders:
            raise RuntimeError("No searchable iCloud mail folders were returned.")

        for folder in folders:
            escaped_name = folder.replace("\\", "\\\\").replace('"', '\\"')
            mailbox_argument = "INBOX" if folder.upper() == "INBOX" else '"' + escaped_name + '"'
            status, _ = client.select(mailbox_argument, readonly=True)
            if status != "OK":
                reasons.append(f"Could not search the iCloud folder {folder}.")
                continue

            searched: set[str] = set()
            pending = list(seeds[:MAX_THREAD_SEEDS])
            while pending and len(processed) < MAX_THREAD_MESSAGES:
                seed = pending.pop(0)
                if seed in searched:
                    continue
                searched.add(seed)
                for header in ("Message-ID", "References", "In-Reply-To"):
                    status, data = client.uid(
                        "SEARCH", None, "HEADER", header, _imap_quote(seed)
                    )
                    if status != "OK":
                        reasons.append(f"iCloud search failed in {folder}.")
                        continue
                    uids = (data[0] or b"").split() if data else []
                    for uid in uids:
                        uid_text = uid.decode(errors="ignore") if isinstance(uid, bytes) else str(uid)
                        identity = (folder, uid_text)
                        if identity in processed:
                            continue
                        processed.add(identity)
                        status, payload = client.uid("FETCH", uid, "(BODY.PEEK[] FLAGS)")
                        if status != "OK" or not payload or not isinstance(payload[0], tuple):
                            reasons.append(f"An iCloud message could not be retrieved from {folder}.")
                            continue

                        raw = payload[0][1]
                        metadata = payload[0][0] if isinstance(payload[0][0], bytes) else str(payload[0][0]).encode()
                        parsed = email.message_from_bytes(raw)
                        provider_id = (parsed.get("Message-ID") or "").strip()
                        if not provider_id:
                            reasons.append("An iCloud thread message had no RFC Message-ID and was skipped.")
                            continue

                        for candidate in _message_ids(parsed.get("References")) + _message_ids(parsed.get("In-Reply-To")):
                            if candidate not in searched and candidate not in pending and len(searched) + len(pending) < MAX_THREAD_SEEDS:
                                pending.append(candidate)
                        child_id = provider_id
                        if child_id not in searched and child_id not in pending and len(searched) + len(pending) < MAX_THREAD_SEEDS:
                            pending.append(child_id)

                        received = _received_at(parsed.get("Date"))
                        body = providers._plain_body(parsed)
                        refs = parsed.get("References") or parsed.get("In-Reply-To") or stable_root
                        has_attachments = any(
                            part.get_filename() or part.get_content_disposition() == "attachment"
                            for part in (parsed.walk() if parsed.is_multipart() else [])
                        )
                        values = {
                            "thread_key": stable_root,
                            "sender": providers.decode_mime(parsed.get("From")),
                            "recipients": ", ".join(value for value in (
                                providers.decode_mime(parsed.get("To")),
                                providers.decode_mime(parsed.get("Cc")),
                            ) if value),
                            "subject": providers.decode_mime(parsed.get("Subject")),
                            "received_at": received,
                            "snippet": body[:240],
                            "body_text": body,
                            "is_read": b"\\Seen" in metadata,
                            "has_attachments": has_attachments,
                            "is_trashed": False,
                        }
                        saved = db.scalar(select(EmailMessage).where(
                            EmailMessage.account_id == account.id,
                            EmailMessage.provider_message_id == provider_id,
                        ))
                        if saved:
                            for key, value in values.items():
                                setattr(saved, key, value)
                        else:
                            db.add(EmailMessage(
                                user_id=account.user_id,
                                account_id=account.id,
                                provider_message_id=provider_id,
                                **values,
                            ))
                            imported += 1
                        db.flush()

            if len(processed) >= MAX_THREAD_MESSAGES:
                reasons.append(f"iCloud thread retrieval reached the {MAX_THREAD_MESSAGES}-message limit.")
                break
            if len(seeds) > MAX_THREAD_SEEDS:
                reasons.append(f"iCloud thread retrieval reached the {MAX_THREAD_SEEDS}-identity search limit.")
                break

        rows = _thread_messages(db, account, stable_root)
        db.commit()
        return rows, not reasons, list(dict.fromkeys(reasons)), imported
    finally:
        try:
            client.logout()
        except Exception:
            pass


def load_provider_thread(db: Session, account: EmailAccount, source: EmailMessage):
    """Return (chronological messages, provider_scan_complete, partial_reasons, imported_count)."""
    if account.provider == "gmail":
        return _gmail_thread(db, account, source)
    if account.provider == "icloud":
        return _icloud_thread(db, account, source)
    raise RuntimeError("Unsupported email provider.")
