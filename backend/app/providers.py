import imaplib,email,re
from email.header import decode_header
from email.utils import parsedate_to_datetime
from datetime import datetime,timedelta,timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import EmailAccount,EmailMessage
from .security import get_fernet

def decode_mime(value:str|None)->str:
    if not value:return ""
    pieces=[]
    for part,charset in decode_header(value):
        pieces.append(part.decode(charset or "utf-8",errors="replace") if isinstance(part,bytes) else part)
    return "".join(pieces)

def extract_body(msg)->str:
    chunks=[]
    parts=msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        if part.get_content_maintype()=="multipart" or part.get_content_disposition()=="attachment":continue
        if part.get_content_type()=="text/plain":
            data=part.get_payload(decode=True) or b""
            chunks.append(data.decode(part.get_content_charset() or "utf-8",errors="replace"))
    return "\n".join(chunks).strip()

def sync_icloud(db:Session,account:EmailAccount)->int:
    if not account.encrypted_secret:raise RuntimeError("iCloud app-specific password is missing.")
    password=get_fernet().decrypt(account.encrypted_secret.encode()).decode()
    client=imaplib.IMAP4_SSL("imap.mail.me.com",993,timeout=30)
    try:
        client.login(account.email,password)
        client.select("INBOX",readonly=True)
        since=(datetime.now(timezone.utc)-timedelta(days=90)).strftime("%d-%b-%Y")
        status,ids=client.search(None,"SINCE",since)
        if status!="OK":raise RuntimeError("Mailbox search failed.")
        imported=0
        for uid in ids[0].split()[-500:]:
            status,payload=client.fetch(uid,"(BODY.PEEK[] FLAGS)")
            if status!="OK" or not payload or not isinstance(payload[0],tuple):continue
            raw=payload[0][1]
            header=payload[0][0].decode("utf-8",errors="replace") if isinstance(payload[0][0],bytes) else str(payload[0][0])
            msg=email.message_from_bytes(raw)
            provider_id=msg.get("Message-ID") or uid.decode()
            if db.scalar(select(EmailMessage).where(EmailMessage.account_id==account.id,EmailMessage.provider_message_id==provider_id)):continue
            try:
                received=parsedate_to_datetime(msg.get("Date")) if msg.get("Date") else datetime.now(timezone.utc)
                if received.tzinfo is None:received=received.replace(tzinfo=timezone.utc)
            except Exception:received=datetime.now(timezone.utc)
            body=extract_body(msg)
            refs=msg.get("References") or msg.get("In-Reply-To") or provider_id
            db.add(EmailMessage(user_id=account.user_id,account_id=account.id,provider_message_id=provider_id,
                thread_key=str(refs)[:500],sender=decode_mime(msg.get("From")),recipients=decode_mime(msg.get("To")),
                subject=decode_mime(msg.get("Subject")),received_at=received,snippet=body[:240],body_text=body[:200000],
                current_summary="",thread_summary="",is_read=bool(re.search(r"\\Seen",header,re.I)),
                has_attachments=any(p.get_content_disposition()=="attachment" for p in (msg.walk() if msg.is_multipart() else []))))
            imported+=1
        account.last_sync_at=datetime.now(timezone.utc)
        account.connection_status="connected"
        db.commit()
        return imported
    finally:
        try:client.logout()
        except Exception:pass
