from datetime import datetime
from zoneinfo import ZoneInfo
from app.worker import due_sync_slots

def test_due_schedule_slot_within_grace_window():
    now = datetime(2026, 11, 16, 8, 12, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert due_sync_slots(now, ["08:00", "11:00"], grace_minutes=30) == ["08:00"]

def test_schedule_slot_not_queued_before_its_time():
    now = datetime(2026, 11, 16, 7, 59, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert due_sync_slots(now, ["08:00"], grace_minutes=30) == []

def test_custom_schedule_and_invalid_values():
    now = datetime(2026, 11, 16, 14, 23, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert due_sync_slots(now, ["14:10", "25:00", "14:10"], grace_minutes=30) == ["14:10"]
