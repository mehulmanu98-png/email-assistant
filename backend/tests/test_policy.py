from datetime import datetime,timedelta,timezone
from app.policy import effective_priority

def test_hard_deadline_becomes_urgent_inside_24_hours():
    now=datetime.now(timezone.utc)
    assert effective_priority("normal",now+timedelta(hours=12),"hard",False,now)=="urgent"

def test_hard_deadline_becomes_high_inside_72_hours():
    now=datetime.now(timezone.utc)
    assert effective_priority("normal",now+timedelta(hours=48),"hard",False,now)=="high"

def test_target_deadline_never_becomes_urgent_by_deadline_alone():
    now=datetime.now(timezone.utc)
    assert effective_priority("normal",now-timedelta(hours=1),"target",False,now)=="high"

def test_manual_priority_overrides_deadline_escalation():
    now=datetime.now(timezone.utc)
    assert effective_priority("low",now-timedelta(hours=1),"hard",True,now)=="low"

def test_missing_deadline_does_not_escalate():
    assert effective_priority("normal",None,"hard",False)=="normal"
