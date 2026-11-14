from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from typing import Literal

Priority = Literal["urgent", "high", "normal", "low"]

class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=200)

class AccountIn(BaseModel):
    provider: Literal["icloud"]
    email: EmailStr
    app_password: str = Field(min_length=8, max_length=200)

class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    instructions: str = Field(default="", max_length=10000)
    priority: Priority = "normal"
    deadline_type: Literal["hard", "target"] | None = None
    deadline_at: datetime | None = None
    scheduled_start_at: datetime | None = None

class TaskPriorityIn(BaseModel):
    priority: Priority | None = None
    automatic: bool = False

class FollowUpIn(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=10000)
    owner: str = Field(default="", max_length=200)
    due_at: datetime | None = None
    message_id: int | None = None
    status: Literal["action_required", "awaiting_response"] = "action_required"

class FollowUpPatchIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=10000)
    owner: str | None = Field(default=None, max_length=200)
    due_at: datetime | None = None
    status: Literal["action_required", "awaiting_response", "completed"] | None = None
    snoozed_until: datetime | None = None

class DraftIn(BaseModel):
    to: list[EmailStr] = Field(default_factory=list)
    cc: list[EmailStr] = Field(default_factory=list)
    bcc: list[EmailStr] = Field(default_factory=list)
    subject: str = Field(default="", max_length=998)
    body: str = Field(default="", max_length=100000)

class SendApprovalIn(BaseModel):
    confirm_send: bool
    expected_updated_at: datetime

class ConversationIn(BaseModel):
    title: str = Field(default="New conversation", max_length=500)

class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=20000)


class UserSettingsPatchIn(BaseModel):
    sync_times: list[str] = Field(min_length=1, max_length=6)
    timezone: str = Field(min_length=1, max_length=64)
