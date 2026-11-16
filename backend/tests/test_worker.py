from datetime import datetime
from zoneinfo import ZoneInfo
from app.worker import due_sync_slots

def test_due_slots_include_missed_earlier_schedule_times():
    now = datetime(2026, 11, 16, 11, 42, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert due_sync_slots(now, ["08:00", "11:00", "14:00"]) == ["08:00", "11:00"]

def test_schedule_slot_not_queued_before_its_time():
    now = datetime(2026, 11, 16, 7, 59, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert due_sync_slots(now, ["08:00"]) == []

def test_custom_schedule_and_invalid_values():
    now = datetime(2026, 11, 16, 14, 23, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert due_sync_slots(now, ["14:10", "25:00", "14:10"]) == ["14:10"]

def test_sync_retry_delay_is_exponential_and_bounded():
    from app.worker import retry_delay
    from datetime import timedelta
    assert retry_delay(1) == timedelta(minutes=5)
    assert retry_delay(2) == timedelta(minutes=10)
    assert retry_delay(3) == timedelta(minutes=20)

def test_worker_lease_prevents_overlapping_runner_and_releases(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.db import Base
    import app.worker as worker

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(worker, "SessionLocal", factory)

    first = worker.acquire_worker_lease()
    assert first
    assert worker.acquire_worker_lease() is None
    # An expired lease can be reclaimed after an interrupted execution.
    from app.models import WorkerLease
    from datetime import timedelta, timezone
    db = factory()
    lease = db.get(WorkerLease, worker.WORKER_LEASE_NAME)
    lease.lease_until = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    db.close()

    second = worker.acquire_worker_lease()
    assert second and second != first
    worker.release_worker_lease(first)
    assert worker.acquire_worker_lease() is None
    worker.release_worker_lease(second)
    third = worker.acquire_worker_lease()
    assert third
    worker.release_worker_lease(third)
    engine.dispose()
