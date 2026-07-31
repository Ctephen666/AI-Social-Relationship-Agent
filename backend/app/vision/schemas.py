from datetime import datetime

from pydantic import BaseModel, Field


class OCRBlock(BaseModel):
    text: str
    confidence: float
    box: list[list[int]] = Field(default_factory=list)


class ContactObservation(BaseModel):
    nickname: str
    last_message_time_text: str = ""
    last_message_preview: str = ""
    interaction_days: int | None = None
    status: str = "unknown"
    confidence: float = 0.0


class ScanObservation(BaseModel):
    source: str = "screen"
    captured_at: datetime
    image_path: str | None = None
    blocks: list[OCRBlock] = Field(default_factory=list)
    contacts: list[ContactObservation] = Field(default_factory=list)

