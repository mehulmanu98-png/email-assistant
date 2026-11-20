import argparse
import logging
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError
from .db import SessionLocal, init_db
from .models import SyncJob, EmailAccount, ScheduleRun, UserSettings, WorkerLease, ReplyDraft, ForwardDraft, OutboundDraft, EmailMessage
from .providers import sync_icloud, send_icloud, send_icloud_forward
from .gmail import sync_gmail, send_gmail, send_gmail_forward
from .conversation_sync import append_linked_email_messages
from .config import settings
from .ai_enrichment import enrich_synced_messages

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("email-assistant-worker")
MAX_SYNC_ATTEMPTS = 3
WORKER_LEASE_NAME = "mailbox-sync"
WORKER_LEASE_MINUTES = 20


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def acquire_worker_lease() -> str | None:
    """Claim the singleton mailbox worker lease in Neon before processing jobs."""
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        lease = db.scalar(
            select(WorkerLease).where(WorkerLease.lease_name == WORKER_LEASE_NAME).with_for_update()
        )
        if lease and _as_utc(lease.lease_until) > now:
            return None
        if lease:
            lease.owner_token = token
            lease.lease_until = now + timedelta(minutes=WORKER_LEASE_MINUTES)
        else:
            db.add(WorkerLease(
                lease_name=WORKER_LEASE_NAME,
                owner_token=token,
                lease_until=now + timedelta(minutes=WORKER_LEASE_MINUTES)
            ))
        try:
            db.commit()
        except IntegrityError:
            # Two first-time invocations raced to create the unique singleton row.
            db.rollback()
            return None
        return token
    finally:
        db.close()


def release_worker_lease(token: str) -> None:
    """Release only the lease owned by this execution; never clear another runner's lock."""
    db = SessionLocal()
    try:
        lease = db.scalar(select(WorkerLease).where(
            WorkerLease.lease_name == WORKER_LEASE_NAME,
            WorkerLease.owner_token == token
        ).with_for_update())
        if lease:
            db.delete(lease)
            db.commit()
    finally:
        db.close()


def retry_delay(attempt_count: int) -> timedelta:
    """Bound transient sync retries with short exponential backoff."""
    return timedelta(minutes=5 * (2 ** max(0, attempt_count - 1)))


def due_sync_slots(now_local: datetime, times: list[str]) -> list[str]:
    """Return every configured slot due today; late runners catch up missed slots."""
    if now_local.tzinfo is None:
        raise ValueError("now_local must be timezone-aware")
    due = []
    for raw in times:
        value = str(raw).strip()
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            log.warning("Ignoring invalid mailbox sync time %r", value)
            continue
        hour, minute = map(int, value.split(":"))
        scheduled = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if scheduled <= now_local:
            due.append(value)
    return sorted(set(due))


def run_once() -> bool:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        job = db.scalar(select(SyncJob).where(
            SyncJob.status == "queued",
            or_(SyncJob.available_at.is_(None), SyncJob.available_at <= now)
        ).order_by(SyncJob.id).with_for_update(skip_locked=True))
        if not job:
            return False
        job.status = "running"
        job.attempt_count = (job.attempt_count or 0) + 1
        db.commit()
        account = db.get(EmailAccount, job.account_id)
        if not account or account.connection_status == "disconnected":
            job.status = "failed"
            job.details = "Account is disconnected."
            db.commit()
            return True
        try:
            if account.provider == "icloud":
                count = sync_icloud(db, account)
            elif account.provider == "gmail":
                count = sync_gmail(db, account, settings.max_messages_per_sync)
            else:
                raise RuntimeError("Unsupported provider.")
            linked_updates = append_linked_email_messages(db, account.id)
            enrichment = enrich_synced_messages(db, account, batch_size=20)
            job.status = "completed"
            job.details = (
                f"Imported {count} new messages; appended {linked_updates} new message(s) "
                f"to linked conversations; AI summaries processed {enrichment.get('processed', 0)}, "
                f"failed {enrichment.get('failed', 0)}."
                + (f" AI skipped: {enrichment['skipped']}." if enrichment.get("skipped") else "")
            )
        except Exception as exc:
            if job.attempt_count < MAX_SYNC_ATTEMPTS:
                delay = retry_delay(job.attempt_count)
                job.status = "queued"
                job.available_at = datetime.now(timezone.utc) + delay
                job.details = f"Sync attempt {job.attempt_count} failed ({type(exc).__name__}); retry queued."
                log.warning("Sync attempt %s failed for account %s; retry in %s (%s)",
                            job.attempt_count, account.id, delay, type(exc).__name__)
            else:
                job.status = "failed"
                job.details = f"Sync failed after {job.attempt_count} attempts ({type(exc).__name__}). Check account connection and server configuration."
                account.connection_status = "error"
                log.warning("Sync failed permanently for account %s (%s)", account.id, type(exc).__name__)
        db.commit()
        return True
    finally:
        db.close()



def run_send_once() -> bool:
    """Send one user-approved draft from the background runner.

    A draft is changed to 'sending' and committed before network I/O. If the
    provider result is ambiguous, it is marked 'send_uncertain' and is never
    automatically retried, preventing duplicate outgoing email.
    """
    db = SessionLocal()
    try:
        candidates = [
            db.scalar(select(ReplyDraft).where(ReplyDraft.status == "queued")
                      .order_by(ReplyDraft.id).limit(1).with_for_update(skip_locked=True)),
            db.scalar(select(ForwardDraft).where(ForwardDraft.status == "queued")
                      .order_by(ForwardDraft.id).limit(1).with_for_update(skip_locked=True)),
            db.scalar(select(OutboundDraft).where(OutboundDraft.status == "queued")
                      .order_by(OutboundDraft.id).limit(1).with_for_update(skip_locked=True)),
        ]
        draft = next((item for item in candidates if item is not None), None)
        if draft is None:
            return False
        draft.status = "sending"
        db.commit()

        if isinstance(draft, OutboundDraft):
            account = db.scalar(select(EmailAccount).where(
                EmailAccount.id == draft.account_id,
                EmailAccount.user_id == draft.user_id,
                EmailAccount.connection_status != "disconnected",
            ))
            source = None
        else:
            source = db.scalar(select(EmailMessage).where(
                EmailMessage.id == draft.message_id,
                EmailMessage.user_id == draft.user_id,
            ))
            account = db.get(EmailAccount, source.account_id) if source else None
            if account and (account.user_id != draft.user_id or account.connection_status == "disconnected"):
                account = None

        if not account:
            draft.status = "failed"
            db.commit()
            log.warning("Approved send draft %s could not be sent because its source account is unavailable.", draft.id)
            return True

        try:
            if isinstance(draft, ForwardDraft):
                if not source:
                    raise RuntimeError("Original message unavailable.")
                if account.provider == "icloud":
                    provider_id = send_icloud_forward(
                        account, list(draft.to_json or []), list(draft.cc_json or []),
                        list(draft.bcc_json or []), draft.subject, draft.body, source,
                        draft.include_attachments,
                    )
                elif account.provider == "gmail":
                    provider_id = send_gmail_forward(
                        db, account, list(draft.to_json or []), list(draft.cc_json or []),
                        list(draft.bcc_json or []), draft.subject, draft.body, source,
                        draft.include_attachments,
                    )
                else:
                    raise RuntimeError("Unsupported provider.")
            elif isinstance(draft, ReplyDraft):
                if not source:
                    raise RuntimeError("Original message unavailable.")
                if account.provider == "icloud":
                    provider_id = send_icloud(
                        account, list(draft.to_json or []), list(draft.cc_json or []),
                        list(draft.bcc_json or []), draft.subject, draft.body, source,
                    )
                elif account.provider == "gmail":
                    provider_id = send_gmail(
                        db, account, list(draft.to_json or []), list(draft.cc_json or []),
                        list(draft.bcc_json or []), draft.subject, draft.body, source,
                    )
                else:
                    raise RuntimeError("Unsupported provider.")
            else:
                if account.provider == "icloud":
                    provider_id = send_icloud(
                        account, list(draft.to_json or []), list(draft.cc_json or []),
                        list(draft.bcc_json or []), draft.subject, draft.body, None, draft.attachments_json or [],
                    )
                elif account.provider == "gmail":
                    provider_id = send_gmail(
                        db, account, list(draft.to_json or []), list(draft.cc_json or []),
                        list(draft.bcc_json or []), draft.subject, draft.body, None, draft.attachments_json or [],
                    )
                else:
                    raise RuntimeError("Unsupported provider.")
        except Exception as exc:
            draft.status = "send_uncertain"
            db.commit()
            log.warning("Approved send draft %s has an uncertain provider result (%s); automatic retry disabled.",
                        draft.id, type(exc).__name__)
            return True

        draft.status = "sent"
        draft.provider_sent_id = provider_id
        db.commit()
        log.info("Approved send draft %s was accepted by its provider.", draft.id)
        return True
    finally:
        db.close()


def recover_stale_jobs(stale_minutes: int = WORKER_LEASE_MINUTES + 5) -> int:
    """Requeue jobs left running when an ephemeral runner was interrupted."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)
    db = SessionLocal()
    try:
        rows = db.scalars(select(SyncJob).where(SyncJob.status == "running", SyncJob.updated_at < cutoff)).all()
        for item in rows:
            if (item.attempt_count or 0) >= MAX_SYNC_ATTEMPTS:
                item.status = "failed"
                item.details = "Sync stopped after repeated worker interruptions. Start a new manual sync to retry."
            else:
                item.status = "queued"
                item.available_at = datetime.now(timezone.utc)
                item.details = "Recovered after an interrupted background worker."
        count = len(rows)
        db.commit()
        return count
    finally:
        db.close()


def schedule_due_syncs() -> int:
    # Mailbox synchronisation only; AI review and notifications are deliberately disabled.
    db = SessionLocal()
    try:
        user_rows = db.execute(
            select(EmailAccount.user_id, UserSettings.sync_times, UserSettings.timezone)
            .join(UserSettings, UserSettings.user_id == EmailAccount.user_id, isouter=True)
            .where(EmailAccount.connection_status != "disconnected")
        ).all()
        grouped = {}
        for user_id, times, timezone_name in user_rows:
            grouped[user_id] = (
                times or [v.strip() for v in settings.auto_sync_times.split(",") if v.strip()],
                timezone_name or settings.timezone
            )
        queued = 0
        for user_id, (times, timezone_name) in grouped.items():
            try:
                now_local = datetime.now(ZoneInfo(timezone_name))
            except ZoneInfoNotFoundError:
                log.warning("Invalid timezone for user %s; using configured default.", user_id)
                now_local = datetime.now(ZoneInfo(settings.timezone))
            for slot in due_sync_slots(now_local, times):
                key = f"{user_id}:{now_local.strftime('%Y-%m-%d')}:{slot}"
                if db.scalar(select(ScheduleRun.id).where(ScheduleRun.run_key == key)):
                    continue
                db.add(ScheduleRun(run_key=key))
                accounts = db.scalars(select(EmailAccount).where(
                    EmailAccount.user_id == user_id,
                    EmailAccount.connection_status != "disconnected"
                )).all()
                for account in accounts:
                    db.add(SyncJob(user_id=user_id, account_id=account.id, status="queued",
                                   details=f"Scheduled mailbox sync ({slot} {timezone_name}; AI review disabled)."))
                    queued += 1
        db.commit()
        return queued
    finally:
        db.close()


def run_scheduled_batch(max_jobs: int = 100) -> int:
    """One-shot entry point for a cloud scheduler invocation."""
    init_db()
    lease_token = acquire_worker_lease()
    if not lease_token:
        log.info("Another mailbox worker execution holds the Neon lease; skipping this overlapping trigger.")
        return 0
    try:
        recovered = recover_stale_jobs()
        added = schedule_due_syncs()
        if recovered:
            log.warning("Recovered %s interrupted job(s).", recovered)
        if added:
            log.info("Queued %s scheduled sync job(s).", added)
        processed = 0
        while processed < max_jobs:
            did_send = run_send_once()
            did_sync = run_once()
            if not did_send and not did_sync:
                break
            processed += int(did_send) + int(did_sync)
        log.info("Background runner finished; processed %s mailbox/send job(s).", processed)
        return processed
    finally:
        release_worker_lease(lease_token)


def main() -> None:
    init_db()
    log.info("Worker running: mailbox sync enabled; AI execution and notifications disabled.")
    while True:
        try:
            schedule_due_syncs()
            did_send = run_send_once()
            did_sync = run_once()
            if not did_send and not did_sync:
                time.sleep(15)
        except Exception:
            log.exception("Worker cycle error")
            time.sleep(15)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scheduled-once", action="store_true",
                        help="Run the scheduler and drain queued mailbox jobs, then exit.")
    args = parser.parse_args()
    if args.scheduled_once:
        run_scheduled_batch()
    else:
        main()
