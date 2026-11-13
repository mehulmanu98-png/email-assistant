import logging
import time
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .db import SessionLocal, init_db
from .models import SyncJob, EmailAccount, ScheduleRun
from .providers import sync_icloud
from .gmail import sync_gmail
from .config import settings

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("email-assistant-worker")

def run_once():
    db = SessionLocal()
    try:
        job = db.scalar(select(SyncJob).where(SyncJob.status == "queued").order_by(SyncJob.id).with_for_update(skip_locked=True))
        if not job:
            return False
        job.status = "running"
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
                raise RuntimeError("Unsupported email provider.")
            job.status = "completed"
            job.details = f"Imported {count} new messages."
        except Exception as exc:
            job.status = "failed"
            job.details = f"Sync failed ({type(exc).__name__}). Check account connection and server configuration."
            account.connection_status = "error"
            log.warning("Mail sync failed for account %s (%s)", account.id, type(exc).__name__)
        db.commit()
        return True
    finally:
        db.close()

def schedule_due_syncs():
    # This is mailbox synchronization only. It does not perform AI review or send notifications.
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo(settings.timezone))
    slots = [v.strip() for v in settings.auto_sync_times.split(",") if v.strip()]
    if now.strftime("%H:%M") not in slots:
        return
    key = now.strftime("%Y-%m-%d-%H-%M")
    db = SessionLocal()
    try:
        if db.scalar(select(ScheduleRun.id).where(ScheduleRun.run_key == key)):
            return
        db.add(ScheduleRun(run_key=key))
        db.flush()
        accounts = db.scalars(select(EmailAccount).where(EmailAccount.connection_status != "disconnected")).all()
        for account in accounts:
            db.add(SyncJob(user_id=account.user_id, account_id=account.id, status="queued",
                           details="Scheduled mailbox sync (no AI processing)."))
        db.commit()
    except IntegrityError:
        db.rollback()
    finally:
        db.close()

def main():
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
    main()
