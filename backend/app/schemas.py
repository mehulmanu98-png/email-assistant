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

class EmailAIAssistIn(BaseModel):
    mode: Literal["draft", "rephrase", "grammar", "ask", "chat", "summary", "thread_summary"]
    instruction: str = Field(default="", max_length=6000)
    draft_body: str = Field(default="", max_length=30000)
    history: list[dict] = Field(default_factory=list, max_length=12)


class SendApprovalIn(BaseModel):
    confirm_send: bool
    expected_updated_at: datetime


class OutboundDraftIn(DraftIn):
    account_id: int = Field(gt=0)
    attachments: list[dict] = Field(default_factory=list, max_length=10)


class ReadStateIn(BaseModel):
    is_read: bool

class ForwardDraftIn(DraftIn):
    include_attachments: bool = True


class AppleEnrollmentCreateIn(BaseModel):
    device_name: str = Field(min_length=1, max_length=200)


class AppleDeviceEnrollIn(BaseModel):
    enrollment_token: str = Field(min_length=32, max_length=200)
    device_name: str = Field(min_length=1, max_length=200)


class AppleCommandIn(BaseModel):
    command_type: Literal["note", "reminder"]
    title: str = Field(min_length=1, max_length=500)
    body: str = Field(default="", max_length=20000)
    due_at: datetime | None = None
    timezone: str = Field(default="Asia/Kolkata", min_length=1, max_length=64)
    message_id: int | None = None
    device_id: int | None = Field(default=None, gt=0)
    idempotency_key: str = Field(min_length=16, max_length=100)


class AppleDeviceCommandResultIn(BaseModel):
    lease_token: str = Field(min_length=32, max_length=200)
    success: bool
    native_record_id: str | None = Field(default=None, max_length=500)
    error_message: str = Field(default="", max_length=2000)


class ConversationIn(BaseModel):
    title: str = Field(default="New conversation", max_length=500)

class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=20000)

class ConversationLinkIn(BaseModel):
    conversation_id: int = Field(gt=0)
    auto_update: bool = True


class UserSettingsPatchIn(BaseModel):
    sync_times: list[str] = Field(min_length=1, max_length=6)
    timezone: str = Field(min_length=1, max_length=64)

class AttachmentSummaryIn(BaseModel):
    attachment_indexes: list[int] = Field(min_length=1, max_length=10)

class ActivityLogIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
