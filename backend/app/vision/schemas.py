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


class StructuredChatObject(ContactObservation):
    """Vision Parser output. It can be persisted or passed to the Agent unchanged."""

    bounds: list[int] = Field(default_factory=list)
    raw_text: list[str] = Field(default_factory=list)


class ScanObservation(BaseModel):
    source: str = "screen"
    captured_at: datetime
    image_path: str | None = None
    blocks: list[OCRBlock] = Field(default_factory=list)
    contacts: list[StructuredChatObject] = Field(default_factory=list)
