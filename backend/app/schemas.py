from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.database.models import Priority, SuggestionStatus


class UserCreate(BaseModel):
    nickname: str = Field(min_length=1, max_length=100)
    relationship: str = Field(default="朋友", max_length=100)
    priority: Priority = Priority.medium
    tags: list[str] = Field(default_factory=list)


class UserUpdate(BaseModel):
    relationship: str | None = None
    priority: Priority | None = None
    tags: list[str] | None = None


class UserRead(UserCreate):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class InteractionCreate(BaseModel):
    time: datetime | None = None
    content: str = ""
    status: str = "manual"


class InteractionRead(BaseModel):
    id: int
    user_id: int
    time: datetime
    content: str
    status: str
    source: str
    model_config = ConfigDict(from_attributes=True)


class MemoryCreate(BaseModel):
    facts: str = Field(min_length=1)
    preferences: str = ""


class MemoryRead(MemoryCreate):
    id: int
    user_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class SuggestionRead(BaseModel):
    id: int
    user_id: int
    nickname: str | None = None
    content: str
    tone: str
    reason: str
    risk_level: str
    status: SuggestionStatus
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class SuggestionUpdate(BaseModel):
    status: SuggestionStatus


class ScanRequest(BaseModel):
    region: tuple[int, int, int, int] | None = None
    dry_run: bool = False


class ScanRead(BaseModel):
    id: int
    status: str
    source: str
    screenshot_path: str | None
    result_count: int
    error: str | None
    created_at: datetime
    completed_at: datetime | None
    model_config = ConfigDict(from_attributes=True)


class DashboardRead(BaseModel):
    today_needing_attention: int
    high_priority_users: list[UserRead]
    pending_suggestions: int
    recent_interactions: list[InteractionRead]


class SettingsRead(BaseModel):
    scan_time: str = "09:00"
    scan_frequency: str = "daily"
    ocr_region: list[int] | None = None
    keep_screenshots: bool = False
    llm_configured: bool = False


class SettingsUpdate(BaseModel):
    scan_time: str | None = None
    scan_frequency: str | None = None
    ocr_region: list[int] | None = None
    keep_screenshots: bool | None = None

