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
