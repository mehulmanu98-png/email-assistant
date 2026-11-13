import time, logging
from sqlalchemy import select
from .db import SessionLocal,init_db
from .models import SyncJob,EmailAccount
from .providers import sync_icloud

logging.basicConfig(level=logging.INFO)
log=logging.getLogger("email-assistant-worker")

def run_once():
    db=SessionLocal()
    try:
        job=db.scalar(select(SyncJob).where(SyncJob.status=="queued").order_by(SyncJob.id).with_for_update(skip_locked=True))
        if not job:return False
        job.status="running";db.commit()
        account=db.get(EmailAccount,job.account_id)
        if not account or account.connection_status=="disconnected":
            job.status="failed";job.details="Account is disconnected.";db.commit();return True
        if account.provider!="icloud":
            job.status="failed";job.details="Provider adapter is unavailable.";db.commit();return True
        try:
            count=sync_icloud(db,account)
            job.status="completed";job.details=f"Imported {count} messages. Limited Inbox-only import; review completion checklist."
        except Exception as exc:
            job.status="failed";job.details=f"Sync failed: {type(exc).__name__}: {str(exc)[:250]}"
            account.connection_status="error"
        db.commit()
        return True
    finally:db.close()

def main():
    init_db()
    log.info("Worker running. AI task execution and scheduled mailbox review are not implemented.")
    while True:
        try:
            if not run_once():time.sleep(5)
        except Exception:
            log.exception("Worker cycle error");time.sleep(10)

if __name__=="__main__":main()
