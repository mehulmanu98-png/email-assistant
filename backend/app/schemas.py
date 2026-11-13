from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from typing import Literal

Priority = Literal["urgent", "high", "normal", "low"]

class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=200)

class AccountIn(BaseModel):
    provider: Literal["icloud", "gmail"]
    email: EmailStr
    app_password: str | None = Field(default=None, min_length=8, max_length=200)

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
    description: str = ""
    owner: str = ""
    due_at: datetime | None = None
    message_id: int | None = None
    status: Literal["action_required", "awaiting_response"] = "action_required"

class DraftIn(BaseModel):
    to: list[EmailStr] = []
    cc: list[EmailStr] = []
    bcc: list[EmailStr] = []
    subject: str = ""
    body: str = Field(default="", max_length=100000)

class ConversationIn(BaseModel):
    title: str = Field(default="New conversation", max_length=500)

class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
