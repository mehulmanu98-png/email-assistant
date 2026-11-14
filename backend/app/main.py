import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from email.utils import getaddresses
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Depends, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy import select, desc, func
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db, init_db
from .models import (
    User, EmailAccount, EmailMessage, ReplyDraft, FollowUp, AITask,
    AIConversation, SyncJob, OAuthState, BlockedSender, UserSettings, utcnow
)
from .security import (
    hash_password, verify_password, create_access_token, current_user,
    get_fernet, COOKIE_NAME
)
from .schemas import (
    LoginIn, AccountIn, TaskIn, TaskPriorityIn, FollowUpIn, FollowUpPatchIn,
    DraftIn, SendApprovalIn, ConversationIn, MessageIn, UserSettingsPatchIn
)
from .policy import effective_priority
from .providers import set_icloud_read, move_icloud_to_trash, send_icloud
from .gmail import set_gmail_read, trash_gmail, send_gmail

app = FastAPI(title=settings.app_name, version="0.2.0")
app.add_middleware(
    CORSMiddleware, allow_origins=[settings.frontend_origin], allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type"]
)

@app.middleware("http")
async def origin_guard(request: Request, call_next):
    if request.method in {"POST", "PATCH", "DELETE", "PUT"}:
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != settings.frontend_origin.rstrip("/"):
            return Response("Origin not allowed", status_code=403)
    return await call_next(request)

@app.on_event("startup")
def startup():
    if settings.app_env == "production":
        if settings.jwt_secret == "development-only-change-this-secret" or len(settings.jwt_secret) < 32:
            raise RuntimeError("Production requires a random JWT_SECRET of at least 32 characters.")
        if len(settings.field_encryption_key) < 24:
            raise RuntimeError("Production requires a dedicated FIELD_ENCRYPTION_KEY seed.")
        if len(settings.bootstrap_password) < 12:
            raise RuntimeError("BOOTSTRAP_PASSWORD must contain at least 12 characters.")
    init_db()
    db = next(get_db())
    try:
        if not db.scalar(select(User).limit(1)):
            db.add(User(email=settings.bootstrap_email.lower(), password_hash=hash_password(settings.bootstrap_password)))
            db.commit()
    finally:
        db.close()

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "providers": {"icloud": "imap_smtp", "gmail": "google_oauth"},
        "ai_ready": False,
        "ai_status": "disabled_plan_not_eligible",
        "scheduled_mailbox_sync": True,
        "notifications": False
    }

@app.post("/api/auth/login")
def login(data: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    response.set_cookie(
        COOKIE_NAME, create_access_token(user.id), httponly=True,
        secure=settings.app_env == "production", samesite="strict", max_age=43200, path="/"
    )
    return {"email": user.email}

@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="strict")
    return {"ok": True}

@app.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email}

@app.get("/api/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    def count(model, *criteria):
        return db.scalar(select(func.count()).select_from(model).where(*criteria)) or 0
    return {
        "accounts": count(EmailAccount, EmailAccount.user_id == user.id),
        "unread": count(EmailMessage, EmailMessage.user_id == user.id, EmailMessage.is_read.is_(False), EmailMessage.is_trashed.is_(False)),
        "followups": count(FollowUp, FollowUp.user_id == user.id, FollowUp.status.in_(["action_required", "awaiting_response"])),
        "active_tasks": count(AITask, AITask.user_id == user.id, AITask.status.in_(["queued", "in_progress", "waiting_for_user"])),
        "ai_ready": False
    }

@app.get("/api/settings")
def get_user_settings(user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = db.scalar(select(UserSettings).where(UserSettings.user_id == user.id))
    if not item:
        item = UserSettings(
            user_id=user.id,
            sync_times=[v.strip() for v in settings.auto_sync_times.split(",") if v.strip()],
            timezone=settings.timezone
        )
        db.add(item)
        db.commit()
        db.refresh(item)
    return {
        "sync_times": item.sync_times, "timezone": item.timezone,
        "ai_processing_enabled": False, "notifications_enabled": False
    }

@app.patch("/api/settings")
def update_user_settings(data: UserSettingsPatchIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    import re
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    times = sorted(set(data.sync_times))
    if len(times) != len(data.sync_times) or any(
        not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value) for value in times
    ):
        raise HTTPException(422, "Enter unique 24-hour times in HH:MM format.")
    try:
        ZoneInfo(data.timezone)
    except ZoneInfoNotFoundError:
        raise HTTPException(422, "Choose a valid IANA timezone.")
    item = db.scalar(select(UserSettings).where(UserSettings.user_id == user.id))
    if not item:
        item = UserSettings(user_id=user.id)
        db.add(item)
    item.sync_times = times
    item.timezone = data.timezone
    db.commit()
    return {
        "sync_times": item.sync_times, "timezone": item.timezone,
        "ai_processing_enabled": False, "notifications_enabled": False
    }

@app.get("/api/accounts")
def accounts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(EmailAccount).where(EmailAccount.user_id == user.id).order_by(EmailAccount.id)).all()
    return [{
        "id": a.id, "provider": a.provider, "email": a.email,
        "status": a.connection_status, "last_sync_at": a.last_sync_at
    } for a in rows]

@app.post("/api/accounts")
def add_account(data: AccountIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    address = data.email.lower()
    existing = db.scalar(select(EmailAccount).where(
        EmailAccount.user_id == user.id, EmailAccount.email == address
    ))
    encrypted = get_fernet().encrypt(data.app_password.encode()).decode()
    if existing:
        if existing.provider != "icloud":
            raise HTTPException(409, "This address is already connected through another provider.")
        existing.encrypted_secret = encrypted
        existing.connection_status = "pending_verification"
        account = existing
    else:
        account = EmailAccount(
            user_id=user.id, provider="icloud", email=address,
            encrypted_secret=encrypted, connection_status="pending_verification"
        )
        db.add(account)
    db.commit()
    db.refresh(account)
    db.add(SyncJob(user_id=user.id, account_id=account.id, status="queued", details="Initial 90-day iCloud Inbox sync"))
    db.commit()
    return {"id": account.id, "status": "verification_queued"}

@app.get("/api/oauth/gmail/start")
def gmail_oauth_start(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(503, "Gmail OAuth is not configured. Add Google OAuth client credentials to the private server environment.")
    state = secrets.token_urlsafe(36)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    db.add(OAuthState(
        user_id=user.id, state=state, code_verifier=verifier,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
    ))
    db.commit()
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/gmail.send",
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256"
    }
    return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params), status_code=302)

@app.get("/api/oauth/gmail/callback")
def gmail_oauth_callback(
    code: str | None = None, state: str | None = None, error: str | None = None,
    db: Session = Depends(get_db)
):
    finish = settings.frontend_origin.rstrip("/") + "/"
    if error:
        return RedirectResponse(finish + "?gmail=cancelled", status_code=302)
    if not code or not state:
        return RedirectResponse(finish + "?gmail=failed", status_code=302)
    saved = db.scalar(select(OAuthState).where(OAuthState.state == state, OAuthState.used.is_(False)))
    now = datetime.now(timezone.utc)
    if not saved or (saved.expires_at.replace(tzinfo=timezone.utc) if saved.expires_at.tzinfo is None else saved.expires_at) < now:
        return RedirectResponse(finish + "?gmail=invalid_state", status_code=302)
    saved.used = True
    db.commit()
    try:
        token_response = httpx.post("https://oauth2.googleapis.com/token", data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "code": code,
            "code_verifier": saved.code_verifier,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code"
        }, timeout=30)
        if token_response.status_code != 200:
            return RedirectResponse(finish + "?gmail=token_failed", status_code=302)
        token_data = token_response.json()
        if "refresh_token" not in token_data:
            return RedirectResponse(finish + "?gmail=offline_access_missing", status_code=302)
        profile_response = httpx.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": "Bearer " + token_data["access_token"]}, timeout=20
        )
        if profile_response.status_code != 200:
            return RedirectResponse(finish + "?gmail=profile_failed", status_code=302)
        profile = profile_response.json()
        address = str(profile.get("email", "")).lower()
        if not address or profile.get("verified_email") is False:
            return RedirectResponse(finish + "?gmail=email_not_verified", status_code=302)
        account = db.scalar(select(EmailAccount).where(
            EmailAccount.user_id == saved.user_id, EmailAccount.email == address
        ))
        if account and account.provider != "gmail":
            return RedirectResponse(finish + "?gmail=address_conflict", status_code=302)
        expiry = datetime.now(timezone.utc).timestamp() + int(token_data.get("expires_in", 3600))
        credentials = {
            "access_token": token_data["access_token"],
            "refresh_token": token_data["refresh_token"],
            "expires_at": expiry,
            "scope": token_data.get("scope", "")
        }
        encrypted = get_fernet().encrypt(__import__("json").dumps(credentials).encode()).decode()
        if account:
            account.encrypted_secret = encrypted
            account.connection_status = "pending_verification"
        else:
            account = EmailAccount(
                user_id=saved.user_id, provider="gmail", email=address,
                encrypted_secret=encrypted, connection_status="pending_verification"
            )
            db.add(account)
        db.commit()
        db.refresh(account)
        db.add(SyncJob(
            user_id=saved.user_id, account_id=account.id, status="queued",
            details="Initial 90-day Gmail sync"
        ))
        db.commit()
        return RedirectResponse(finish + "?gmail=connected", status_code=302)
    except Exception:
        db.rollback()
        return RedirectResponse(finish + "?gmail=failed", status_code=302)

@app.delete("/api/accounts/{account_id}")
def disconnect_account(account_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    account = db.scalar(select(EmailAccount).where(
        EmailAccount.id == account_id, EmailAccount.user_id == user.id
    ))
    if not account:
        raise HTTPException(404, "Account not found")
    account.encrypted_secret = None
    account.connection_status = "disconnected"
    db.commit()
    return {"status": "disconnected", "history_retained": True}

@app.post("/api/sync")
def sync_all(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(EmailAccount).where(
        EmailAccount.user_id == user.id, EmailAccount.connection_status != "disconnected"
    )).all()
    for account in rows:
        db.add(SyncJob(user_id=user.id, account_id=account.id, status="queued", details="Manual sync"))
    db.commit()
    return {"queued": len(rows)}

@app.post("/api/sync/{account_id}")
def sync_one(account_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    account = db.scalar(select(EmailAccount).where(
        EmailAccount.id == account_id, EmailAccount.user_id == user.id
    ))
    if not account:
        raise HTTPException(404, "Account not found")
    if account.connection_status == "disconnected":
        raise HTTPException(409, "Reconnect this account before syncing.")
    db.add(SyncJob(user_id=user.id, account_id=account.id, status="queued", details="Manual sync"))
    db.commit()
    return {"queued": True}

@app.get("/api/sync/jobs")
def sync_jobs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(SyncJob).where(SyncJob.user_id == user.id).order_by(desc(SyncJob.id)).limit(30)).all()
    return [{
        "id": x.id, "account_id": x.account_id, "status": x.status,
        "details": x.details, "created_at": x.created_at
    } for x in rows]

def _email_address(value: str) -> str:
    addresses = getaddresses([value or ""])
    return addresses[0][1].lower() if addresses else ""

def _blocked_addresses(db: Session, user_id: int) -> list[str]:
    return [x.address.lower() for x in db.scalars(select(BlockedSender).where(BlockedSender.user_id == user_id)).all()]

@app.get("/api/messages")
def messages(
    q: str = "", account_id: int | None = None, unread: bool = False,
    user: User = Depends(current_user), db: Session = Depends(get_db)
):
    stmt = select(EmailMessage).where(
        EmailMessage.user_id == user.id, EmailMessage.is_trashed.is_(False)
    )
    if account_id:
        stmt = stmt.where(EmailMessage.account_id == account_id)
    if unread:
        stmt = stmt.where(EmailMessage.is_read.is_(False))
    if q:
        needle = "%" + q[:200] + "%"
        stmt = stmt.where(
            EmailMessage.subject.ilike(needle) |
            EmailMessage.sender.ilike(needle) |
            EmailMessage.body_text.ilike(needle)
        )
    rows = db.scalars(stmt.order_by(desc(EmailMessage.received_at), desc(EmailMessage.id)).limit(500)).all()
    blocked = _blocked_addresses(db, user.id)
    return [{
        "id": x.id, "account_id": x.account_id, "sender": x.sender,
        "recipients": x.recipients, "subject": x.subject, "received_at": x.received_at,
        "snippet": x.snippet, "summary": x.current_summary, "thread_summary": x.thread_summary,
        "priority": x.priority, "priority_reason": x.priority_reason,
        "is_read": x.is_read, "has_attachments": x.has_attachments
    } for x in rows if not any(address and address in x.sender.lower() for address in blocked)]

@app.get("/api/messages/{message_id}")
def message_detail(message_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(EmailMessage).where(
        EmailMessage.id == message_id, EmailMessage.user_id == user.id
    ))
    if not row or row.is_trashed:
        raise HTTPException(404, "Email not found")
    account = db.get(EmailAccount, row.account_id)
    return {
        "id": row.id, "account_id": row.account_id, "account_email": account.email if account else "",
        "sender": row.sender, "recipients": row.recipients, "subject": row.subject,
        "received_at": row.received_at, "body_text": row.body_text,
        "summary": row.current_summary, "thread_summary": row.thread_summary,
        "is_read": row.is_read, "has_attachments": row.has_attachments
    }

@app.post("/api/messages/{message_id}/read")
def mark_read(message_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(EmailMessage).where(
        EmailMessage.id == message_id, EmailMessage.user_id == user.id
    ))
    if not row or row.is_trashed:
        raise HTTPException(404, "Email not found")
    account = db.get(EmailAccount, row.account_id)
    if not account:
        raise HTTPException(409, "Source account is unavailable.")
    try:
        if account.provider == "icloud":
            confirmed = set_icloud_read(account, row.provider_message_id, True)
        elif account.provider == "gmail":
            confirmed = set_gmail_read(db, account, row.provider_message_id, True)
        else:
            raise RuntimeError("Unsupported provider.")
        if not confirmed:
            raise RuntimeError("Provider did not confirm the read-state change.")
    except Exception as exc:
        raise HTTPException(502, f"Provider could not confirm the read-state change ({type(exc).__name__}).")
    row.is_read = True
    db.commit()
    return {"is_read": True, "provider_sync": "confirmed"}

@app.delete("/api/messages/{message_id}")
def delete_message(message_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(EmailMessage).where(
        EmailMessage.id == message_id, EmailMessage.user_id == user.id
    ))
    if not row or row.is_trashed:
        raise HTTPException(404, "Email not found")
    account = db.get(EmailAccount, row.account_id)
    if not account:
        raise HTTPException(409, "Source account is unavailable.")
    try:
        if account.provider == "icloud":
            confirmed = move_icloud_to_trash(account, row.provider_message_id)
        elif account.provider == "gmail":
            confirmed = trash_gmail(db, account, row.provider_message_id)
        else:
            raise RuntimeError("Unsupported provider.")
        if not confirmed:
            raise RuntimeError("Provider did not confirm moving the email to Trash.")
    except Exception as exc:
        raise HTTPException(502, f"Provider could not confirm moving the email to Trash ({type(exc).__name__}).")
    row.is_trashed = True
    db.commit()
    return {"trashed": True, "provider_sync": "confirmed"}

@app.post("/api/messages/{message_id}/block")
def block_sender(message_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(EmailMessage).where(
        EmailMessage.id == message_id, EmailMessage.user_id == user.id
    ))
    if not row:
        raise HTTPException(404, "Email not found")
    address = _email_address(row.sender)
    if not address:
        raise HTTPException(422, "This message has no usable sender address.")
    existing = db.scalar(select(BlockedSender).where(
        BlockedSender.user_id == user.id, BlockedSender.address == address
    ))
    if not existing:
        db.add(BlockedSender(user_id=user.id, address=address))
        db.commit()
    return {"blocked": address, "scope": "app_only", "provider_blocking": False}

def draft_out(draft: ReplyDraft, account: EmailAccount | None = None):
    return {
        "id": draft.id, "message_id": draft.message_id,
        "to": draft.to_json, "cc": draft.cc_json, "bcc": draft.bcc_json,
        "subject": draft.subject, "body": draft.body, "status": draft.status,
        "updated_at": draft.updated_at, "from_account": account.email if account else None
    }

@app.post("/api/messages/{message_id}/draft")
def create_draft(message_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    source = db.scalar(select(EmailMessage).where(
        EmailMessage.id == message_id, EmailMessage.user_id == user.id
    ))
    if not source:
        raise HTTPException(404, "Email not found")
    account = db.get(EmailAccount, source.account_id)
    draft = db.scalar(select(ReplyDraft).where(
        ReplyDraft.message_id == message_id, ReplyDraft.user_id == user.id
    ))
    if not draft:
        sender = _email_address(source.sender)
        to_values = [sender] if sender else []
        own = account.email.lower() if account else ""
        cc_values = []
        for _, addr in getaddresses([source.recipients or ""]):
            addr = addr.lower()
            if addr and addr != own and addr != sender and addr not in cc_values:
                cc_values.append(addr)
        subject = source.subject if source.subject.lower().startswith("re:") else "Re: " + source.subject
        draft = ReplyDraft(
            user_id=user.id, message_id=source.id,
            to_json=to_values, cc_json=cc_values, subject=subject, body=""
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)
    return draft_out(draft, account)

@app.patch("/api/drafts/{draft_id}")
def save_draft(draft_id: int, data: DraftIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    draft = db.scalar(select(ReplyDraft).where(
        ReplyDraft.id == draft_id, ReplyDraft.user_id == user.id
    ))
    if not draft:
        raise HTTPException(404, "Draft not found")
    if draft.status in {"sent", "sending", "send_uncertain"}:
        raise HTTPException(409, "This draft can no longer be edited because sending has started or completed.")
    draft.to_json = [str(v) for v in data.to]
    draft.cc_json = [str(v) for v in data.cc]
    draft.bcc_json = [str(v) for v in data.bcc]
    draft.subject = data.subject
    draft.body = data.body
    draft.status = "draft"
    db.commit()
    db.refresh(draft)
    source = db.get(EmailMessage, draft.message_id)
    account = db.get(EmailAccount, source.account_id) if source else None
    return draft_out(draft, account)

@app.post("/api/drafts/{draft_id}/send")
def send_draft(
    draft_id: int, approval: SendApprovalIn,
    user: User = Depends(current_user), db: Session = Depends(get_db)
):
    draft = db.scalar(select(ReplyDraft).where(
        ReplyDraft.id == draft_id, ReplyDraft.user_id == user.id
    ).with_for_update())
    if not draft:
        raise HTTPException(404, "Draft not found")
    if not approval.confirm_send:
        raise HTTPException(400, "Explicit send confirmation is required.")
    if draft.status == "sent":
        raise HTTPException(409, "This draft has already been accepted by the provider.")
    if draft.status in {"sending", "send_uncertain"}:
        raise HTTPException(409, "The previous send result is uncertain. Check the source account's Sent folder before retrying.")
    actual = draft.updated_at
    if actual and actual.tzinfo is None:
        actual = actual.replace(tzinfo=timezone.utc)
    expected = approval.expected_updated_at
    if expected.tzinfo is None:
        expected = expected.replace(tzinfo=timezone.utc)
    if not actual or abs((actual - expected).total_seconds()) > 2:
        raise HTTPException(409, "The draft changed after it was displayed. Save and review the latest version before sending.")
    recipients = list(draft.to_json or []) + list(draft.cc_json or []) + list(draft.bcc_json or [])
    if not recipients:
        raise HTTPException(422, "Add at least one recipient before sending.")
    if not draft.subject.strip() or not draft.body.strip():
        raise HTTPException(422, "Subject and message body must not be empty.")
    source = db.scalar(select(EmailMessage).where(
        EmailMessage.id == draft.message_id, EmailMessage.user_id == user.id
    ))
    if not source:
        raise HTTPException(409, "Original email was removed; sending is blocked.")
    account = db.scalar(select(EmailAccount).where(
        EmailAccount.id == source.account_id, EmailAccount.user_id == user.id
    ))
    if not account or account.connection_status == "disconnected":
        raise HTTPException(409, "Reconnect the original source account. The From account cannot be changed.")
    # Persist a one-way state before network I/O so duplicate clicks cannot send twice.
    draft.status = "sending"
    db.commit()
    try:
        if account.provider == "icloud":
            provider_id = send_icloud(
                account, list(draft.to_json or []), list(draft.cc_json or []),
                list(draft.bcc_json or []), draft.subject, draft.body, source
            )
        elif account.provider == "gmail":
            provider_id = send_gmail(
                db, account, list(draft.to_json or []), list(draft.cc_json or []),
                list(draft.bcc_json or []), draft.subject, draft.body, source
            )
        else:
            raise RuntimeError("Unsupported provider.")
    except Exception as exc:
        draft.status = "send_uncertain"
        db.commit()
        raise HTTPException(502, f"The provider send result could not be confirmed ({type(exc).__name__}). Check Sent before retrying.")
    draft.status = "sent"
    draft.provider_sent_id = provider_id
    db.commit()
    return {"status": "sent", "provider_accepted": True, "delivery_confirmed": False,
            "note": "The source provider accepted the message; final delivery is not confirmed."}

@app.get("/api/followups")
def followups(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(FollowUp).where(
        FollowUp.user_id == user.id,
        FollowUp.status.in_(["action_required", "awaiting_response"])
    ).order_by(FollowUp.due_at)).all()
    return [{
        "id": x.id, "title": x.title, "description": x.description,
        "owner": x.owner, "due_at": x.due_at, "status": x.status,
        "message_id": x.message_id, "snoozed_until": x.snoozed_until
    } for x in rows if not x.snoozed_until or x.snoozed_until <= utcnow()]

@app.post("/api/followups")
def add_followup(data: FollowUpIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if data.message_id and not db.scalar(select(EmailMessage).where(
        EmailMessage.id == data.message_id, EmailMessage.user_id == user.id
    )):
        raise HTTPException(404, "Source email not found")
    item = FollowUp(user_id=user.id, **data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "title": item.title, "description": item.description, "owner": item.owner,
            "due_at": item.due_at, "status": item.status, "message_id": item.message_id}

@app.patch("/api/followups/{followup_id}")
def edit_followup(
    followup_id: int, data: FollowUpPatchIn,
    user: User = Depends(current_user), db: Session = Depends(get_db)
):
    item = db.scalar(select(FollowUp).where(
        FollowUp.id == followup_id, FollowUp.user_id == user.id
    ))
    if not item:
        raise HTTPException(404, "Follow-up not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    db.commit()
    return {"updated": True}

@app.patch("/api/followups/{followup_id}/complete")
def complete_followup(followup_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = db.scalar(select(FollowUp).where(
        FollowUp.id == followup_id, FollowUp.user_id == user.id
    ))
    if not item:
        raise HTTPException(404, "Follow-up not found")
    item.status = "completed"
    db.commit()
    return {"completed": True}

@app.patch("/api/followups/{followup_id}/snooze")
def snooze_followup(followup_id: int, until: datetime, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = db.scalar(select(FollowUp).where(
        FollowUp.id == followup_id, FollowUp.user_id == user.id
    ))
    if not item:
        raise HTTPException(404, "Follow-up not found")
    item.snoozed_until = until
    db.commit()
    return {"snoozed_until": until}

@app.delete("/api/followups/{followup_id}")
def remove_followup(followup_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = db.scalar(select(FollowUp).where(
        FollowUp.id == followup_id, FollowUp.user_id == user.id
    ))
    if not item:
        raise HTTPException(404, "Follow-up not found")
    db.delete(item)
    db.commit()
    return {"removed": True, "email_retained": True}

def task_out(task: AITask):
    return {
        "id": task.id, "title": task.title, "instructions": task.instructions,
        "status": task.status, "priority": task.effective_priority,
        "base_priority": task.base_priority, "priority_override_by_user": task.priority_override_by_user,
        "deadline_type": task.deadline_type, "deadline_at": task.deadline_at,
        "scheduled_start_at": task.scheduled_start_at, "reason": task.priority_reason,
        "blocker": task.execution_blocker, "created_at": task.created_at
    }

@app.get("/api/tasks")
def tasks(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AITask).where(AITask.user_id == user.id).order_by(desc(AITask.created_at))).all()
    return [task_out(x) for x in rows]

@app.post("/api/tasks")
def add_task(data: TaskIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    priority = effective_priority(data.priority, data.deadline_at, data.deadline_type, False)
    item = AITask(
        user_id=user.id, title=data.title, instructions=data.instructions,
        base_priority=data.priority, effective_priority=priority,
        deadline_type=data.deadline_type, deadline_at=data.deadline_at,
        scheduled_start_at=data.scheduled_start_at,
        priority_reason="Calculated from the saved priority and deadline rules.",
        execution_blocker="AI execution is paused: the current Go plan is not eligible for the official open-source ChatGPT plan-usage route."
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return task_out(item)

@app.patch("/api/tasks/{task_id}/priority")
def set_priority(task_id: int, data: TaskPriorityIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = db.scalar(select(AITask).where(AITask.id == task_id, AITask.user_id == user.id))
    if not item:
        raise HTTPException(404, "Task not found")
    if data.automatic:
        item.priority_override_by_user = False
        item.effective_priority = effective_priority(item.base_priority, item.deadline_at, item.deadline_type, False)
        item.priority_reason = "Automatic priority restored from saved base priority and deadline."
    else:
        if not data.priority:
            raise HTTPException(422, "Select a priority or reset to Automatic.")
        item.priority_override_by_user = True
        item.effective_priority = data.priority
        item.priority_reason = "Manually set by user; automatic deadline escalation is suspended."
    db.commit()
    return task_out(item)

@app.patch("/api/tasks/{task_id}/cancel")
def cancel_task(task_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = db.scalar(select(AITask).where(AITask.id == task_id, AITask.user_id == user.id))
    if not item:
        raise HTTPException(404, "Task not found")
    item.status = "cancelled"
    db.commit()
    return task_out(item)

@app.get("/api/conversations")
def conversations(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AIConversation).where(
        AIConversation.user_id == user.id
    ).order_by(desc(AIConversation.updated_at))).all()
    return [{"id": x.id, "title": x.title, "updated_at": x.updated_at} for x in rows]

@app.post("/api/conversations")
def create_conversation(data: ConversationIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = AIConversation(user_id=user.id, title=data.title, messages=[])
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "title": item.title, "messages": item.messages}

@app.get("/api/conversations/{conversation_id}")
def conversation_detail(conversation_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = db.scalar(select(AIConversation).where(
        AIConversation.id == conversation_id, AIConversation.user_id == user.id
    ))
    if not item:
        raise HTTPException(404, "Conversation not found")
    return {"id": item.id, "title": item.title, "messages": item.messages}

@app.post("/api/conversations/{conversation_id}/messages")
def conversation_message(
    conversation_id: int, data: MessageIn,
    user: User = Depends(current_user), db: Session = Depends(get_db)
):
    item = db.scalar(select(AIConversation).where(
        AIConversation.id == conversation_id, AIConversation.user_id == user.id
    ))
    if not item:
        raise HTTPException(404, "Conversation not found")
    history = list(item.messages or [])
    history.append({"role": "user", "content": data.content, "at": utcnow().isoformat()})
    history.append({
        "role": "system",
        "content": "Saved locally. AI responses are unavailable because this account's current ChatGPT Go plan is not eligible for the official open-source plan-usage integration. No paid API is enabled.",
        "at": utcnow().isoformat()
    })
    item.messages = history
    db.commit()
    return {"id": item.id, "title": item.title, "messages": item.messages, "ai_reply_available": False}
