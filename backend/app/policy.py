from datetime import datetime, timezone
PRIORITIES = ("urgent", "high", "normal", "low")
RANK = {name: i for i, name in enumerate(PRIORITIES)}

def effective_priority(base_priority: str, deadline_at: datetime | None,
                       deadline_type: str | None, manual_override: bool,
                       now: datetime | None = None) -> str:
    if base_priority not in RANK:
        base_priority = "normal"
    if manual_override or not deadline_at or deadline_type not in ("hard", "target"):
        return base_priority
    now = now or datetime.now(timezone.utc)
    due = deadline_at if deadline_at.tzinfo else deadline_at.replace(tzinfo=timezone.utc)
    hours = (due - now).total_seconds() / 3600
    floor = None
    if deadline_type == "hard":
        if hours <= 24: floor = "urgent"
        elif hours <= 72: floor = "high"
    elif hours <= 24:
        floor = "high"
    if floor and RANK[floor] < RANK[base_priority]:
        return floor
    return base_priority
