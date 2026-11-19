import base64
import hashlib
import hmac
import secrets
import re
import logging
from datetime import datetime, timedelta, timezone
from email.utils import getaddresses
from urllib.parse import urlencode, quote

import httpx
from fastapi import FastAPI, Depends, HTTPException, Response, Request, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from sqlalchemy import select, desc, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db, init_db, SessionLocal
from .models import (
    User, EmailAccount, EmailMessage, EmailActionJob, ReplyDraft, ForwardDraft, OutboundDraft, FollowUp, AITask,
    AIConversation, SyncJob, OAuthState, BlockedSender, UserSettings, LoginThrottle, AppleDevice,
    AppleDeviceEnrollment, AppleDeviceCommand, utcnow
)
from .security import (
    hash_password, verify_password, create_access_token, current_user,
    get_fernet, COOKIE_NAME
)
from .schemas import (
    LoginIn, AccountIn, TaskIn, TaskPriorityIn, FollowUpIn, FollowUpPatchIn,
    DraftIn, ForwardDraftIn, OutboundDraftIn, SendApprovalIn, ConversationIn, ConversationLinkIn, MessageIn,
    UserSettingsPatchIn, ReadStateIn, AppleEnrollmentCreateIn, AppleDeviceEnrollIn, AppleCommandIn,
    AppleDeviceCommandResultIn
)
from .policy import effective_priority
from .providers import set_icloud_read, set_icloud_starred, move_icloud_to_trash, send_icloud, send_icloud_forward, list_icloud_attachments, get_icloud_attachment
from .gmail import set_gmail_read, set_gmail_starred, trash_gmail, send_gmail, send_gmail_forward, list_gmail_attachments, get_gmail_attachment
from .conversation_sync import get_email_thread_link, link_email_thread, unlink_email_thread
from .cloud_jobs import trigger_mailbox_worker

logger = logging.getLogger("email-assistant-api")
from .thread_retrieval import load_provider_thread

app = FastAPI(title=settings.app_name, version="0.2.0")
app.add_middleware(
    CORSMiddleware, allow_origins=[settings.frontend_origin], allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type"]
)

@app.middleware("http")
async def origin_guard(request: Request, call_next):
    if request.method in {"POST", "PATCH", "DELETE", "PUT"}:
        # Apple Shortcuts authenticate with one-time/enrolled device tokens rather
        # than the browser session cookie, so they do not send a browser Origin.
        device_token_route = request.url.path.startswith("/api/apple/device/")
        if not device_token_route:
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") != settings.frontend_origin.rstrip("/"):
                return Response("Origin not allowed", status_code=403)
            if settings.app_env == "production" and not origin:
                return Response("Origin header is required", status_code=403)
    return await call_next(request)

@app.middleware("http")
async def private_api_response_headers(request: Request, call_next):
    """Prevent browsers and intermediaries from retaining private mailbox API content."""
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "private, no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        if settings.app_env == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.on_event("startup")
def startup():
    if settings.app_env == "production":
        if settings.jwt_secret == "development-only-change-this-secret" or len(settings.jwt_secret) < 32:
            raise RuntimeError("Production requires a random JWT_SECRET of at least 32 characters.")
        if len(settings.field_encryption_key) < 24:
            raise RuntimeError("Production requires a dedicated FIELD_ENCRYPTION_KEY seed.")
        if len(settings.bootstrap_password) < 12 or settings.bootstrap_password == "change-this-password":
            raise RuntimeError("Set a unique BOOTSTRAP_PASSWORD of at least 12 characters.")
        if not settings.frontend_origin.startswith("https://"):
            raise RuntimeError("Production FRONTEND_ORIGIN must use HTTPS.")
        if settings.google_client_id and not settings.google_redirect_uri.startswith("https://"):
            raise RuntimeError("Production GOOGLE_REDIRECT_URI must use HTTPS.")
    init_db()
    db = next(get_db())
    try:
        if not db.scalar(select(User).limit(1)):
            db.add(User(email=settings.bootstrap_email.lower(), password_hash=hash_password(settings.bootstrap_password)))
            db.commit()
    finally:
        db.close()
    # Resume durable provider actions left queued by a prior process restart.
    recovery_db = SessionLocal()
    try:
        pending_ids = recovery_db.scalars(
            select(EmailActionJob.id).where(EmailActionJob.status.in_(["queued", "running"]))
        ).all()
    finally:
        recovery_db.close()
    import threading
    for pending_id in pending_ids:
        threading.Thread(target=_run_email_action_job, args=(pending_id,), daemon=True).start()

@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(select(1))
    except Exception:
        raise HTTPException(503, "Database unavailable")
    return {
        "status": "ok",
        "providers": {"icloud": "imap_smtp", "gmail": "google_oauth"},
        "ai_ready": False,
        "ai_status": "disabled_commercial_integration_not_approved",
        "scheduled_mailbox_sync": True,
        "notifications": False
    }

LOGIN_FAILURE_LIMIT = 5
LOGIN_WINDOW = timedelta(minutes=15)
LOGIN_LOCKOUT = timedelta(minutes=15)
# Equal-cost dummy hash avoids making unknown email addresses much faster to reject.
DUMMY_LOGIN_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


def _login_identifier_hash(email: str) -> str:
    """Hash a normalized sign-in identifier without storing the raw address."""
    return hmac.new(
        settings.jwt_secret.encode("utf-8"),
        email.strip().lower().encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@app.post("/api/auth/login")
def login(data: LoginIn, response: Response, db: Session = Depends(get_db)):
    now = utcnow()
    identifier_hash = _login_identifier_hash(data.email)
    throttle = db.scalar(select(LoginThrottle).where(
        LoginThrottle.identifier_hash == identifier_hash
    ).with_for_update())

    if throttle and throttle.blocked_until and _as_utc(throttle.blocked_until) > now:
        retry_after = max(1, int((_as_utc(throttle.blocked_until) - now).total_seconds()))
        raise HTTPException(
            429,
            "Too many failed sign-in attempts. Wait before trying again.",
            headers={"Retry-After": str(retry_after)},
        )

    if throttle and now - _as_utc(throttle.window_started_at) >= LOGIN_WINDOW:
        throttle.failed_attempts = 0
        throttle.window_started_at = now
        throttle.blocked_until = None

    user = db.scalar(select(User).where(User.email == data.email.lower()))
    password_valid = verify_password(
        data.password,
        user.password_hash if user else DUMMY_LOGIN_PASSWORD_HASH,
    )
    if not user:
        # Do not create durable throttle rows for arbitrary unregistered emails.
        raise HTTPException(401, "Invalid email or password")
    if not password_valid:
        if not throttle:
            throttle = LoginThrottle(
                identifier_hash=identifier_hash,
                failed_attempts=0,
                window_started_at=now,
            )
            db.add(throttle)
            try:
                db.flush()
            except IntegrityError:
                # A parallel first attempt may have created the unique identifier row.
                db.rollback()
                throttle = db.scalar(select(LoginThrottle).where(
                    LoginThrottle.identifier_hash == identifier_hash
                ).with_for_update())
                if not throttle:
                    raise HTTPException(503, "Sign-in is temporarily unavailable. Please retry.")
        throttle.failed_attempts += 1
        throttle.updated_at = now
        if throttle.failed_attempts >= LOGIN_FAILURE_LIMIT:
            throttle.blocked_until = now + LOGIN_LOCKOUT
        db.commit()
        if throttle.blocked_until and _as_utc(throttle.blocked_until) > now:
            raise HTTPException(
                429,
                "Too many failed sign-in attempts. Wait before trying again.",
                headers={"Retry-After": str(int(LOGIN_LOCKOUT.total_seconds()))},
            )
        raise HTTPException(401, "Invalid email or password")

    if throttle:
        db.delete(throttle)
        db.commit()
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
        "active_tasks": count(AITask, AITask.user_id == user.id, AITask.status.in_(["queued", "in_progress"])),
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


def _try_trigger_mailbox_worker() -> bool:
    """Start the durable Cloud Run worker after a job is committed."""
    try:
        return trigger_mailbox_worker()
    except Exception as exc:
        # Never log request bodies, access tokens, mailbox credentials or email content.
        logger.warning(
            "Could not trigger the mailbox worker (%s); the queued job remains available to the scheduled worker.",
            type(exc).__name__,
        )
        return False


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
    worker_triggered = _try_trigger_mailbox_worker()
    return {"id": account.id, "status": "verification_queued", "worker_triggered": worker_triggered}

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
        _try_trigger_mailbox_worker()
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
    worker_triggered = _try_trigger_mailbox_worker() if rows else False
    return {"queued": len(rows), "worker_triggered": worker_triggered}

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
    worker_triggered = _try_trigger_mailbox_worker()
    return {"queued": True, "worker_triggered": worker_triggered}

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
        "is_read": x.is_read, "is_starred": x.is_starred, "has_attachments": x.has_attachments
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
        "is_read": row.is_read, "is_starred": row.is_starred, "has_attachments": row.has_attachments
    }

@app.get("/api/messages/{message_id}/thread")
def message_thread(
    message_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    source = db.scalar(select(EmailMessage).where(
        EmailMessage.id == message_id,
        EmailMessage.user_id == user.id,
        EmailMessage.is_trashed.is_(False),
    ))
    if not source:
        raise HTTPException(404, "Email not found")
    account = db.get(EmailAccount, source.account_id)
    if not account or account.user_id != user.id:
        raise HTTPException(409, "Source email account is unavailable.")
    try:
        rows, provider_scan_complete, partial_reasons, imported_count = load_provider_thread(
            db, account, source
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(502, f"The source provider could not retrieve this email thread ({type(exc).__name__}).")
    return {
        "message_id": source.id,
        "provider": account.provider,
        "account_email": account.email,
        "provider_scan_complete": provider_scan_complete,
        "partial_reasons": partial_reasons,
        "imported_messages": imported_count,
        "message_count": len(rows),
        "read_state_changed": False,
        "messages": [{
            "id": row.id,
            "sender": row.sender,
            "recipients": row.recipients,
            "subject": row.subject,
            "received_at": row.received_at,
            "body_text": row.body_text,
            "is_read": row.is_read,
            "has_attachments": row.has_attachments,
        } for row in rows],
    }


@app.get("/api/messages/{message_id}/attachments")
def message_attachments(
    message_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    row = db.scalar(select(EmailMessage).where(
        EmailMessage.id == message_id,
        EmailMessage.user_id == user.id,
        EmailMessage.is_trashed.is_(False),
    ))
    if not row:
        raise HTTPException(404, "Email not found")
    account = db.get(EmailAccount, row.account_id)
    if not account:
        raise HTTPException(409, "Source email account is unavailable.")
    try:
        if account.provider == "icloud":
            items = list_icloud_attachments(account, row.provider_message_id)
        elif account.provider == "gmail":
            items = list_gmail_attachments(db, account, row.provider_message_id)
        else:
            raise RuntimeError("Unsupported provider.")
        return {"message_id": row.id, "attachments": items}
    except ValueError as exc:
        raise HTTPException(413, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"Original attachments could not be listed ({type(exc).__name__}).")


@app.get("/api/messages/{message_id}/attachments/{attachment_index}")
def message_attachment(
    message_id: int, attachment_index: int, inline: bool = False,
    user: User = Depends(current_user), db: Session = Depends(get_db)
):
    row = db.scalar(select(EmailMessage).where(
        EmailMessage.id == message_id,
        EmailMessage.user_id == user.id,
        EmailMessage.is_trashed.is_(False),
    ))
    if not row:
        raise HTTPException(404, "Email not found")
    account = db.get(EmailAccount, row.account_id)
    if not account:
        raise HTTPException(409, "Source email account is unavailable.")
    try:
        if account.provider == "icloud":
            attachment = get_icloud_attachment(account, row.provider_message_id, attachment_index)
        elif account.provider == "gmail":
            attachment = get_gmail_attachment(db, account, row.provider_message_id, attachment_index)
        else:
            raise RuntimeError("Unsupported provider.")
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(413, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"Original attachment could not be retrieved ({type(exc).__name__}).")

    mime_type = str(attachment.get("mime_type") or "application/octet-stream")
    if "/" not in mime_type or any(ch.isspace() or ord(ch) < 33 or ord(ch) > 126 for ch in mime_type):
        mime_type = "application/octet-stream"
    preview_types = {"application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"}
    can_inline = mime_type in preview_types
    disposition = "inline" if inline and can_inline else "attachment"
    filename = str(attachment.get("filename") or "attachment")
    filename = filename.replace(chr(13), "_").replace(chr(10), "_").replace('"', "_").replace("/", "_").replace(chr(92), "_")
    encoded_filename = quote(filename, safe="")
    content_disposition = f"{disposition}; filename*=UTF-8''{encoded_filename}"
    return Response(
        content=attachment["data"],
        media_type=mime_type,
        headers={
            "Content-Disposition": content_disposition,
            "Content-Length": str(len(attachment["data"])),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


def _run_email_action_job(job_id: int):
    """Execute one durable mailbox action with bounded exponential retries."""
    import time
    delays = [0, 3, 10, 30, 90]
    while True:
        db = SessionLocal()
        try:
            job = db.get(EmailActionJob, job_id)
            if not job or job.status in {"succeeded", "failed"}:
                return
            attempt = int(job.attempt_count or 0) + 1
            if attempt > len(delays):
                job.status = "failed"
                db.commit()
                return
            delay = delays[attempt - 1]
        finally:
            db.close()
        if delay:
            time.sleep(delay)
        db = SessionLocal()
        try:
            job = db.get(EmailActionJob, job_id)
            if not job or job.status in {"succeeded", "failed"}:
                return
            attempt = int(job.attempt_count or 0) + 1
            if attempt > len(delays):
                job.status = "failed"
                db.commit()
                return
            row = db.scalar(select(EmailMessage).where(
                EmailMessage.id == job.message_id, EmailMessage.user_id == job.user_id
            ))
            if not row:
                job.status = "failed"
                job.last_error = "Message no longer exists."
                db.commit()
                return
            account = db.get(EmailAccount, row.account_id)
            if not account:
                raise RuntimeError("Source account unavailable.")
            job.status = "running"
            job.attempt_count = attempt
            db.commit()
            if job.action == "read":
                if account.provider == "icloud":
                    ok = set_icloud_read(account, row.provider_message_id, bool(job.desired_read))
                elif account.provider == "gmail":
                    ok = set_gmail_read(db, account, row.provider_message_id, bool(job.desired_read))
                else:
                    raise RuntimeError("Unsupported provider.")
            elif job.action == "star":
                if account.provider == "icloud":
                    ok = set_icloud_starred(account, row.provider_message_id, bool(job.desired_read))
                elif account.provider == "gmail":
                    ok = set_gmail_starred(db, account, row.provider_message_id, bool(job.desired_read))
                else:
                    raise RuntimeError("Unsupported provider.")
            elif job.action == "trash":
                if account.provider == "icloud":
                    ok = move_icloud_to_trash(account, row.provider_message_id)
                elif account.provider == "gmail":
                    ok = trash_gmail(db, account, row.provider_message_id)
                else:
                    raise RuntimeError("Unsupported provider.")
            else:
                raise RuntimeError("Unsupported mailbox action.")
            if not ok:
                raise RuntimeError("Provider did not confirm the requested action.")
            job.status = "succeeded"
            job.last_error = ""
            db.commit()
            logger.info("Mailbox action job %s succeeded on attempt %s", job_id, attempt)
            return
        except Exception as exc:
            try:
                job = db.get(EmailActionJob, job_id)
                if job:
                    job.status = "queued" if attempt < len(delays) else "failed"
                    job.attempt_count = attempt
                    job.next_attempt_at = utcnow() + timedelta(seconds=(delays[attempt] if attempt < len(delays) else 0))
                    job.last_error = (str(exc).replace("\\n", " ").replace("\\r", " ")[:300]
                                      or type(exc).__name__)
                    db.commit()
            except Exception:
                db.rollback()
            logger.warning("Mailbox action job %s attempt %s failed: %s", job_id, attempt, type(exc).__name__)
            if attempt >= len(delays):
                return
        finally:
            db.close()


def _queue_provider_read_state(background_tasks: BackgroundTasks, row: EmailMessage, db: Session, is_read: bool):
    row.is_read = is_read
    job = _enqueue_email_action(db, row, "read", is_read)
    background_tasks.add_task(_run_email_action_job, job.id)
    return {"is_read": is_read, "provider_sync": "queued", "action_id": job.id}


def _enqueue_email_action(db: Session, row: EmailMessage, action: str, desired_read: bool | None = None):
    job = EmailActionJob(
        user_id=row.user_id, message_id=row.id, action=action,
        desired_read=desired_read, status="queued", attempt_count=0,
        next_attempt_at=utcnow(), last_error=""
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@app.post("/api/messages/{message_id}/read")
def mark_read(message_id: int, background_tasks: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(EmailMessage).where(
        EmailMessage.id == message_id, EmailMessage.user_id == user.id
    ))
    if not row or row.is_trashed:
        raise HTTPException(404, "Email not found")
    return _queue_provider_read_state(background_tasks, row, db, True)


@app.post("/api/messages/{message_id}/read-state")
def update_read_state(
    message_id: int, data: ReadStateIn, background_tasks: BackgroundTasks,
    user: User = Depends(current_user), db: Session = Depends(get_db)
):
    row = db.scalar(select(EmailMessage).where(
        EmailMessage.id == message_id, EmailMessage.user_id == user.id
    ))
    if not row or row.is_trashed:
        raise HTTPException(404, "Email not found")
    return _queue_provider_read_state(background_tasks, row, db, data.is_read)

@app.delete("/api/messages/{message_id}")
def delete_message(message_id: int, background_tasks: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(EmailMessage).where(
        EmailMessage.id == message_id, EmailMessage.user_id == user.id
    ))
    if not row or row.is_trashed:
        raise HTTPException(404, "Email not found")
    row.is_trashed = True
    job = _enqueue_email_action(db, row, "trash")
    background_tasks.add_task(_run_email_action_job, job.id)
    return {"trashed": True, "provider_sync": "queued", "action_id": job.id}


@app.post("/api/messages/{message_id}/star")
def update_starred_state(message_id: int, data: ReadStateIn, background_tasks: BackgroundTasks,
                         user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(EmailMessage).where(
        EmailMessage.id == message_id, EmailMessage.user_id == user.id, EmailMessage.is_trashed.is_(False)
    ))
    if not row:
        raise HTTPException(404, "Email not found")
    row.is_starred = data.is_read
    job = _enqueue_email_action(db, row, "star", data.is_read)
    background_tasks.add_task(_run_email_action_job, job.id)
    return {"is_starred": row.is_starred, "provider_sync": "queued", "action_id": job.id}


@app.get("/api/email-actions/{action_id}")
def get_email_action_status(action_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = db.scalar(select(EmailActionJob).where(
        EmailActionJob.id == action_id, EmailActionJob.user_id == user.id
    ))
    if not job:
        raise HTTPException(404, "Action not found")
    return {
        "id": job.id, "action": job.action, "status": job.status,
        "attempt_count": job.attempt_count, "last_error": job.last_error,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


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

def outbound_draft_out(draft: OutboundDraft, account: EmailAccount | None = None):
    return {
        "id": draft.id,
        "account_id": draft.account_id,
        "to": draft.to_json,
        "cc": draft.cc_json,
        "bcc": draft.bcc_json,
        "subject": draft.subject,
        "body": draft.body,
        "attachments": draft.attachments_json or [],
        "status": draft.status,
        "provider_sent_id": draft.provider_sent_id,
        "created_at": draft.created_at,
        "updated_at": draft.updated_at,
        "from_account": account.email if account else None,
    }


def _owned_connected_account(db: Session, user_id: int, account_id: int):
    account = db.scalar(select(EmailAccount).where(
        EmailAccount.id == account_id,
        EmailAccount.user_id == user_id,
    ))
    if not account or account.connection_status != "connected":
        raise HTTPException(409, "Select a connected email account for the From address.")
    if account.provider not in {"icloud", "gmail"}:
        raise HTTPException(422, "This email provider cannot send outgoing messages.")
    return account


@app.get("/api/outbound-drafts")
def list_outbound_drafts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(OutboundDraft).where(
        OutboundDraft.user_id == user.id,
        OutboundDraft.status.in_(["draft", "queued", "sending", "sent", "send_uncertain", "failed"]),
    ).order_by(desc(OutboundDraft.updated_at)).limit(50)).all()
    output = []
    for row in rows:
        account = db.get(EmailAccount, row.account_id)
        output.append(outbound_draft_out(row, account))
    return output


@app.post("/api/outbound-drafts")
def create_outbound_draft(
    data: OutboundDraftIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    account = _owned_connected_account(db, user.id, data.account_id)
    draft = OutboundDraft(
        user_id=user.id,
        account_id=account.id,
        to_json=[str(value) for value in data.to],
        cc_json=[str(value) for value in data.cc],
        bcc_json=[str(value) for value in data.bcc],
        subject=data.subject,
        body=data.body,
        attachments_json=data.attachments,
        status="draft",
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return outbound_draft_out(draft, account)


@app.patch("/api/outbound-drafts/{draft_id}")
def save_outbound_draft(
    draft_id: int, data: OutboundDraftIn,
    user: User = Depends(current_user), db: Session = Depends(get_db)
):
    draft = db.scalar(select(OutboundDraft).where(
        OutboundDraft.id == draft_id,
        OutboundDraft.user_id == user.id,
    ))
    if not draft:
        raise HTTPException(404, "Outbound draft not found")
    if draft.status in {"sent", "queued", "sending", "send_uncertain"}:
        raise HTTPException(409, "This draft can no longer be edited because sending has started or completed.")
    account = _owned_connected_account(db, user.id, data.account_id)
    draft.account_id = account.id
    draft.to_json = [str(value) for value in data.to]
    draft.cc_json = [str(value) for value in data.cc]
    draft.bcc_json = [str(value) for value in data.bcc]
    draft.subject = data.subject
    draft.body = data.body
    draft.attachments_json = data.attachments
    draft.status = "draft"
    db.commit()
    db.refresh(draft)
    return outbound_draft_out(draft, account)


@app.post("/api/outbound-drafts/{draft_id}/send")
def send_outbound_draft(
    draft_id: int, approval: SendApprovalIn,
    user: User = Depends(current_user), db: Session = Depends(get_db)
):
    draft = db.scalar(select(OutboundDraft).where(
        OutboundDraft.id == draft_id,
        OutboundDraft.user_id == user.id,
    ).with_for_update())
    if not draft:
        raise HTTPException(404, "Outbound draft not found")
    if not approval.confirm_send:
        raise HTTPException(400, "Explicit final approval is required.")
    if draft.status in {"sent", "queued"}:
        raise HTTPException(409, "This email has already been sent or queued for delivery.")
    if draft.status in {"sending", "send_uncertain"}:
        raise HTTPException(409, "The previous send result is uncertain. Check the selected account's Sent folder before retrying.")

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
    account = _owned_connected_account(db, user.id, draft.account_id)

    # Explicit approval queues the immutable reviewed draft for the GitHub-hosted
    # mailbox worker. This keeps provider SMTP off free web hosts that block SMTP.
    draft.status = "queued"
    db.commit()
    return {
        "status": "queued",
        "provider_accepted": False,
        "delivery_confirmed": False,
        "note": "Your approved email is queued for secure background delivery. Check the draft status for the provider result.",
    }


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
    if draft.status in {"sent", "queued", "sending", "send_uncertain"}:
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
    if draft.status in {"sent", "queued"}:
        raise HTTPException(409, "This draft has already been sent or queued for delivery.")
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
    # Explicit approval queues the immutable reviewed draft for the GitHub-hosted
    # mailbox worker. This keeps provider SMTP off free web hosts that block SMTP.
    draft.status = "queued"
    db.commit()
    return {
        "status": "queued",
        "provider_accepted": False,
        "delivery_confirmed": False,
        "note": "Your approved reply is queued for secure background delivery. Check the draft status for the provider result.",
    }


def forward_draft_out(draft: ForwardDraft, account: EmailAccount | None = None):
    return {
        "id": draft.id, "message_id": draft.message_id,
        "to": draft.to_json, "cc": draft.cc_json, "bcc": draft.bcc_json,
        "subject": draft.subject, "body": draft.body,
        "include_attachments": draft.include_attachments,
        "status": draft.status, "updated_at": draft.updated_at,
        "from_account": account.email if account else None,
    }


@app.post("/api/messages/{message_id}/forward")
def create_forward_draft(
    message_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    source = db.scalar(select(EmailMessage).where(
        EmailMessage.id == message_id,
        EmailMessage.user_id == user.id,
        EmailMessage.is_trashed.is_(False),
    ).with_for_update())
    if not source:
        raise HTTPException(404, "Email not found")
    account = db.scalar(select(EmailAccount).where(
        EmailAccount.id == source.account_id,
        EmailAccount.user_id == user.id,
    ))
    if not account:
        raise HTTPException(409, "The original receiving account is unavailable.")
    unresolved = db.scalar(select(ForwardDraft).where(
        ForwardDraft.message_id == message_id,
        ForwardDraft.user_id == user.id,
        ForwardDraft.status.in_(["sending", "send_uncertain"]),
    ).order_by(desc(ForwardDraft.updated_at)))
    if unresolved:
        raise HTTPException(409, "A previous forward has an uncertain send result. Check the source account's Sent folder before creating or sending another forward.")
    draft = db.scalar(select(ForwardDraft).where(
        ForwardDraft.message_id == message_id,
        ForwardDraft.user_id == user.id,
        ForwardDraft.status == "draft",
    ).order_by(desc(ForwardDraft.updated_at)))
    if not draft:
        subject = source.subject if source.subject.lower().startswith("fwd:") else "Fwd: " + source.subject
        draft = ForwardDraft(
            user_id=user.id, message_id=source.id,
            to_json=[], cc_json=[], bcc_json=[],
            subject=subject, body="", include_attachments=True, status="draft",
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)
    return forward_draft_out(draft, account)


@app.patch("/api/forward-drafts/{draft_id}")
def save_forward_draft(
    draft_id: int, data: ForwardDraftIn,
    user: User = Depends(current_user), db: Session = Depends(get_db)
):
    draft = db.scalar(select(ForwardDraft).where(
        ForwardDraft.id == draft_id, ForwardDraft.user_id == user.id
    ))
    if not draft:
        raise HTTPException(404, "Forward draft not found")
    if draft.status in {"sent", "queued", "sending", "send_uncertain"}:
        raise HTTPException(409, "This forward can no longer be edited because sending has started or completed.")
    draft.to_json = [str(v) for v in data.to]
    draft.cc_json = [str(v) for v in data.cc]
    draft.bcc_json = [str(v) for v in data.bcc]
    draft.subject = data.subject
    draft.body = data.body
    draft.include_attachments = data.include_attachments
    draft.status = "draft"
    db.commit()
    db.refresh(draft)
    source = db.get(EmailMessage, draft.message_id)
    account = db.get(EmailAccount, source.account_id) if source else None
    return forward_draft_out(draft, account)


@app.post("/api/forward-drafts/{draft_id}/send")
def send_forward_draft(
    draft_id: int, approval: SendApprovalIn,
    user: User = Depends(current_user), db: Session = Depends(get_db)
):
    draft = db.scalar(select(ForwardDraft).where(
        ForwardDraft.id == draft_id, ForwardDraft.user_id == user.id
    ).with_for_update())
    if not draft:
        raise HTTPException(404, "Forward draft not found")
    if not approval.confirm_send:
        raise HTTPException(400, "Explicit final approval is required.")
    if draft.status in {"sent", "queued"}:
        raise HTTPException(409, "This forward has already been sent or queued for delivery.")
    if draft.status in {"sending", "send_uncertain"}:
        raise HTTPException(409, "The previous send result is uncertain. Check the source account's Sent folder before retrying.")
    actual = draft.updated_at
    if actual and actual.tzinfo is None:
        actual = actual.replace(tzinfo=timezone.utc)
    expected = approval.expected_updated_at
    if expected.tzinfo is None:
        expected = expected.replace(tzinfo=timezone.utc)
    if not actual or abs((actual - expected).total_seconds()) > 2:
        raise HTTPException(409, "The forward changed after it was displayed. Save and review the latest version before sending.")
    recipients = list(draft.to_json or []) + list(draft.cc_json or []) + list(draft.bcc_json or [])
    if not recipients:
        raise HTTPException(422, "Add at least one recipient before forwarding.")
    if not draft.subject.strip():
        raise HTTPException(422, "Subject must not be empty.")
    source = db.scalar(select(EmailMessage).where(
        EmailMessage.id == draft.message_id,
        EmailMessage.user_id == user.id,
        EmailMessage.is_trashed.is_(False),
    ))
    if not source:
        raise HTTPException(409, "Original email is unavailable; forwarding is blocked.")
    account = db.scalar(select(EmailAccount).where(
        EmailAccount.id == source.account_id,
        EmailAccount.user_id == user.id,
    ))
    if not account or account.connection_status == "disconnected":
        raise HTTPException(409, "Reconnect the original source account. The default forward From account is locked to it.")
    # Explicit approval queues the reviewed forward. The background worker sends
    # it from a runner that supports the provider's SMTP requirements.
    draft.status = "queued"
    db.commit()
    return {
        "status": "queued",
        "provider_accepted": False,
        "delivery_confirmed": False,
        "note": "Your approved forward is queued for secure background delivery. Check the draft status for the provider result.",
    }



def _token_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _apple_device_from_token(db: Session, token: str | None) -> AppleDevice:
    if not token:
        raise HTTPException(401, "Apple Shortcut device authentication is required.")
    device = db.scalar(select(AppleDevice).where(
        AppleDevice.token_hash == _token_digest(token),
        AppleDevice.is_active.is_(True),
    ))
    if not device:
        raise HTTPException(401, "This Apple Shortcut device token is invalid or revoked.")
    device.last_seen_at = utcnow()
    return device


def _apple_command_out(command: AppleDeviceCommand) -> dict:
    return {
        "id": command.id,
        "command_type": command.command_type,
        "title": command.payload.get("title", ""),
        "status": command.status,
        "device_id": command.device_id,
        "payload": command.payload,
        "attempts": command.attempts,
        "result": command.result,
        "error_message": command.error_message,
        "created_at": command.created_at,
        "updated_at": command.updated_at,
        "completed_at": command.completed_at,
    }


@app.post("/api/apple/devices/enrollment")
def create_apple_device_enrollment(
    data: AppleEnrollmentCreateIn,
    user: User = Depends(current_user), db: Session = Depends(get_db)
):
    token = secrets.token_urlsafe(36)
    enrollment = AppleDeviceEnrollment(
        user_id=user.id,
        device_name=data.device_name.strip(),
        token_hash=_token_digest(token),
        expires_at=utcnow() + timedelta(minutes=15),
    )
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    # The enrollment code is shown once. Only its hash is stored.
    return {
        "enrollment_token": token,
        "device_name": enrollment.device_name,
        "expires_at": enrollment.expires_at,
        "instructions": "Enter this code once in your private Apple Shortcut enrolment step. It expires in 15 minutes.",
    }


@app.get("/api/apple/devices")
def list_apple_devices(user: User = Depends(current_user), db: Session = Depends(get_db)):
    devices = db.scalars(select(AppleDevice).where(
        AppleDevice.user_id == user.id
    ).order_by(desc(AppleDevice.created_at))).all()
    return [{
        "id": device.id,
        "name": device.name,
        "is_active": device.is_active,
        "created_at": device.created_at,
        "last_seen_at": device.last_seen_at,
        "revoked_at": device.revoked_at,
    } for device in devices]


@app.delete("/api/apple/devices/{device_id}")
def revoke_apple_device(
    device_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    device = db.scalar(select(AppleDevice).where(
        AppleDevice.id == device_id, AppleDevice.user_id == user.id
    ))
    if not device:
        raise HTTPException(404, "Apple Shortcut device not found.")
    if device.is_active:
        device.is_active = False
        device.revoked_at = utcnow()
        db.commit()
    return {"revoked": True, "device_id": device.id}


@app.post("/api/apple/device/enroll")
def enroll_apple_device(data: AppleDeviceEnrollIn, db: Session = Depends(get_db)):
    enrollment = db.scalar(select(AppleDeviceEnrollment).where(
        AppleDeviceEnrollment.token_hash == _token_digest(data.enrollment_token),
    ).with_for_update())
    if not enrollment or enrollment.consumed_at:
        raise HTTPException(401, "Enrollment code is invalid or has already been used.")
    expiry = enrollment.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry <= utcnow():
        raise HTTPException(410, "Enrollment code has expired. Create a new code in Email Assistant settings.")
    device_token = secrets.token_urlsafe(48)
    device = AppleDevice(
        user_id=enrollment.user_id,
        name=data.device_name.strip() or enrollment.device_name,
        token_hash=_token_digest(device_token),
        is_active=True,
    )
    db.add(device)
    enrollment.consumed_at = utcnow()
    db.commit()
    db.refresh(device)
    # Persistent device token is returned once; database stores only its hash.
    return {
        "device_id": device.id,
        "device_name": device.name,
        "device_token": device_token,
        "instructions": "Store this token privately in your personal Shortcut. It will not be shown again and can be revoked from Email Assistant settings.",
    }


@app.post("/api/apple/commands")
def queue_apple_command(
    data: AppleCommandIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    if data.command_type == "note" and not data.body.strip():
        raise HTTPException(422, "A Note needs some content.")
    if data.command_type == "reminder" and not data.due_at:
        raise HTTPException(422, "A Reminder needs a due date and time.")
    if data.message_id and not db.scalar(select(EmailMessage).where(
        EmailMessage.id == data.message_id,
        EmailMessage.user_id == user.id,
    )):
        raise HTTPException(404, "Source email not found.")
    if data.device_id:
        device = db.scalar(select(AppleDevice).where(
            AppleDevice.id == data.device_id,
            AppleDevice.user_id == user.id,
            AppleDevice.is_active.is_(True),
        ))
        if not device:
            raise HTTPException(404, "Selected Apple device is unavailable or revoked.")
    due_at = data.due_at
    if due_at:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            zone = ZoneInfo(data.timezone)
        except ZoneInfoNotFoundError:
            raise HTTPException(422, "Invalid time zone.")
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=zone)
        due_at = due_at.astimezone(timezone.utc)
    payload = {
        "title": data.title.strip(),
        "body": data.body,
        "due_at": due_at.isoformat() if due_at else None,
        "timezone": data.timezone,
        "source_message_id": data.message_id,
        "idempotency_marker": f"[EmailAssistantCommand:{data.idempotency_key}]",
    }
    existing = db.scalar(select(AppleDeviceCommand).where(
        AppleDeviceCommand.user_id == user.id,
        AppleDeviceCommand.idempotency_key == data.idempotency_key,
    ))
    if existing:
        if existing.command_type != data.command_type or existing.payload != payload:
            raise HTTPException(409, "This idempotency key was already used for a different Apple command.")
        return _apple_command_out(existing)
    command = AppleDeviceCommand(
        user_id=user.id,
        device_id=data.device_id,
        command_type=data.command_type,
        payload=payload,
        idempotency_key=data.idempotency_key,
        status="pending_on_device",
    )
    db.add(command)
    try:
        db.commit()
    except Exception:
        db.rollback()
        existing = db.scalar(select(AppleDeviceCommand).where(
            AppleDeviceCommand.user_id == user.id,
            AppleDeviceCommand.idempotency_key == data.idempotency_key,
        ))
        if existing:
            return _apple_command_out(existing)
        raise
    db.refresh(command)
    return _apple_command_out(command)


@app.get("/api/apple/commands")
def list_apple_commands(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AppleDeviceCommand).where(
        AppleDeviceCommand.user_id == user.id
    ).order_by(desc(AppleDeviceCommand.created_at)).limit(100)).all()
    return [_apple_command_out(row) for row in rows]


@app.post("/api/apple/commands/{command_id}/retry")
def retry_apple_command(
    command_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    command = db.scalar(select(AppleDeviceCommand).where(
        AppleDeviceCommand.id == command_id,
        AppleDeviceCommand.user_id == user.id,
    ).with_for_update())
    if not command:
        raise HTTPException(404, "Apple command not found.")
    if command.status != "failed":
        raise HTTPException(409, "Only failed Apple commands can be retried. Pending or leased commands must be allowed to finish.")
    command.status = "pending_on_device"
    command.device_id = None
    command.lease_token_hash = None
    command.lease_expires_at = None
    command.error_message = ""
    command.completed_at = None
    command.result = None
    db.commit()
    db.refresh(command)
    return _apple_command_out(command)


@app.delete("/api/apple/commands/{command_id}")
def cancel_apple_command(
    command_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    command = db.scalar(select(AppleDeviceCommand).where(
        AppleDeviceCommand.id == command_id,
        AppleDeviceCommand.user_id == user.id,
    ).with_for_update())
    if not command:
        raise HTTPException(404, "Apple command not found.")
    if command.status not in {"pending_on_device", "failed"}:
        raise HTTPException(409, "A leased or completed Apple command cannot be cancelled.")
    command.status = "cancelled"
    command.updated_at = utcnow()
    db.commit()
    return {"cancelled": True, "command_id": command.id}


@app.post("/api/apple/device/commands/poll")
def poll_apple_device_commands(
    device_token: str | None = Header(default=None, alias="X-Apple-Device-Token"),
    db: Session = Depends(get_db),
):
    device = _apple_device_from_token(db, device_token)
    now = utcnow()
    command = db.scalar(select(AppleDeviceCommand).where(
        AppleDeviceCommand.user_id == device.user_id,
        (AppleDeviceCommand.device_id.is_(None) | (AppleDeviceCommand.device_id == device.id)),
        (
            AppleDeviceCommand.status == "pending_on_device"
        ) | (
            (AppleDeviceCommand.status == "leased") &
            (AppleDeviceCommand.lease_expires_at <= now)
        ),
    ).order_by(AppleDeviceCommand.created_at).limit(1).with_for_update(skip_locked=True))
    if not command:
        db.commit()
        return {"commands": []}
    lease_token = secrets.token_urlsafe(32)
    command.device_id = device.id
    command.status = "leased"
    command.attempts += 1
    command.lease_token_hash = _token_digest(lease_token)
    command.lease_expires_at = now + timedelta(minutes=3)
    command.updated_at = now
    db.commit()
    return {
        "commands": [{
            "id": command.id,
            "command_type": command.command_type,
            "payload": command.payload,
            "lease_token": lease_token,
            "lease_expires_at": command.lease_expires_at,
        }]
    }


@app.post("/api/apple/device/commands/{command_id}/result")
def submit_apple_device_result(
    command_id: int, data: AppleDeviceCommandResultIn,
    device_token: str | None = Header(default=None, alias="X-Apple-Device-Token"),
    db: Session = Depends(get_db),
):
    device = _apple_device_from_token(db, device_token)
    command = db.scalar(select(AppleDeviceCommand).where(
        AppleDeviceCommand.id == command_id,
        AppleDeviceCommand.user_id == device.user_id,
        AppleDeviceCommand.device_id == device.id,
    ).with_for_update())
    if not command or command.status != "leased":
        raise HTTPException(404, "Leased Apple command not found.")
    if not command.lease_token_hash or not secrets.compare_digest(
        command.lease_token_hash, _token_digest(data.lease_token)
    ):
        raise HTTPException(403, "The command lease token is invalid.")
    lease_expiry = command.lease_expires_at
    if not lease_expiry:
        raise HTTPException(409, "The command lease is no longer valid.")
    if lease_expiry.tzinfo is None:
        lease_expiry = lease_expiry.replace(tzinfo=timezone.utc)
    if lease_expiry <= utcnow():
        raise HTTPException(409, "The command lease expired. Poll again to receive a renewed lease.")
    command.lease_token_hash = None
    command.lease_expires_at = None
    command.updated_at = utcnow()
    if data.success:
        command.status = "completed"
        command.result = {"native_record_id": data.native_record_id}
        command.completed_at = utcnow()
        command.error_message = ""
    else:
        command.status = "failed"
        command.error_message = data.error_message or "The Apple Shortcut reported a failed native action."
        command.result = {"native_record_id": data.native_record_id}
    db.commit()
    return _apple_command_out(command)


@app.get("/api/followups")
def followups(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(FollowUp).where(
        FollowUp.user_id == user.id,
        FollowUp.status.in_(["action_required", "awaiting_response"])
    ).order_by(FollowUp.due_at)).all()
    now = utcnow()
    def is_visible(item: FollowUp) -> bool:
        if not item.snoozed_until:
            return True
        snoozed_until = item.snoozed_until
        if snoozed_until.tzinfo is None:
            snoozed_until = snoozed_until.replace(tzinfo=timezone.utc)
        return snoozed_until <= now
    return [{
        "id": x.id, "title": x.title, "description": x.description,
        "owner": x.owner, "due_at": x.due_at, "status": x.status,
        "message_id": x.message_id, "snoozed_until": x.snoozed_until
    } for x in rows if is_visible(x)]

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
        status="waiting_for_user",
        base_priority=data.priority, effective_priority=priority,
        deadline_type=data.deadline_type, deadline_at=data.deadline_at,
        scheduled_start_at=data.scheduled_start_at,
        priority_reason="Calculated from the saved priority and deadline rules.",
        execution_blocker="AI execution is paused: this app has not received an approved commercial Sign in with ChatGPT integration. The open-source DevKit is noncommercial and is not used for business email processing. No paid API or credit fallback is enabled."
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

@app.get("/api/messages/{message_id}/conversation")
def email_thread_conversation_link(
    message_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    try:
        return get_email_thread_link(db, user.id, message_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc))


@app.post("/api/messages/{message_id}/conversation")
def link_email_to_conversation(
    message_id: int, data: ConversationLinkIn,
    user: User = Depends(current_user), db: Session = Depends(get_db)
):
    try:
        link, appended, total = link_email_thread(
            db, user.id, message_id, data.conversation_id, data.auto_update
        )
        db.commit()
        return {
            "linked": True,
            "link_id": link.id,
            "conversation_id": link.conversation_id,
            "auto_update": link.auto_update,
            "appended_messages": appended,
            "thread_message_count": total,
            "history_retained_on_unlink": True,
        }
    except LookupError as exc:
        db.rollback()
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc))
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(409, str(exc))


@app.delete("/api/messages/{message_id}/conversation")
def unlink_email_from_conversation(
    message_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    try:
        removed = unlink_email_thread(db, user.id, message_id)
        db.commit()
        return {
            "unlinked": removed,
            "conversation_history_retained": True,
            "future_email_updates_stopped": removed,
        }
    except LookupError as exc:
        db.rollback()
        raise HTTPException(404, str(exc))


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
        "content": "Saved locally. AI responses are paused because this app has not received an approved commercial Sign in with ChatGPT integration. The open-source DevKit is noncommercial and is not used for business email processing. No paid API or credit fallback is enabled.",
        "at": utcnow().isoformat()
    })
    item.messages = history
    db.commit()
    return {"id": item.id, "title": item.title, "messages": item.messages, "ai_reply_available": False}


# Cloud Run serves the built React application from the same origin as the API.
# Local Docker Compose continues to serve the frontend through Nginx.
STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.is_dir():
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    def frontend_index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/{frontend_path:path}", include_in_schema=False)
    def frontend_fallback(frontend_path: str):
        if frontend_path == "api" or frontend_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        target = (STATIC_DIR / frontend_path).resolve()
        if STATIC_DIR.resolve() not in target.parents:
            raise HTTPException(404, "Not found")
        if target.is_file():
            return FileResponse(target)
        return FileResponse(STATIC_DIR / "index.html")
