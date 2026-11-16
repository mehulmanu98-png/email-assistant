import argparse
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select, or_
from .db import SessionLocal, init_db
from .models import SyncJob, EmailAccount, ScheduleRun, UserSettings
from .providers import sync_icloud
from .gmail import sync_gmail
from .config import settings

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("email-assistant-worker")
MAX_SYNC_ATTEMPTS = 3


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
            job.status = "completed"
            job.details = f"Imported {count} new messages."
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


def recover_stale_jobs(stale_minutes: int = 45) -> int:
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
            .where(EmailAccount.connection_status != "disconnected").distinct()
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
    """One-shot entry point for an ephemeral GitHub Actions runner."""
    init_db()
    recovered = recover_stale_jobs()
    added = schedule_due_syncs()
    if recovered:
        log.warning("Recovered %s interrupted job(s).", recovered)
    if added:
        log.info("Queued %s scheduled sync job(s).", added)
    processed = 0
    while processed < max_jobs and run_once():
        processed += 1
    log.info("Background runner finished; processed %s job(s).", processed)
    return processed


def main() -> None:
    init_db()
    log.info("Worker running: mailbox sync enabled; AI execution and notifications disabled.")
    while True:
        try:
            schedule_due_syncs()
            if not run_once():
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
