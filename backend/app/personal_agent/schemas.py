from __future__ import annotations

from enum import IntEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class PermissionLevel(IntEnum):
    READ_ONLY = 0
    LOCAL_ACTION = 1
    EXTERNAL_WRITE = 2
    PROHIBITED = 3


class SkillSettingField(BaseModel):
    """Declarative field rendered automatically in the desktop settings UI."""

    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    label: str
    kind: Literal["text", "password", "integer", "number", "boolean", "select"] = "text"
    default: Any = ""
    description: str = ""
    options: list[str] = Field(default_factory=list)


class SkillManifest(BaseModel):
    id: str
    name: str
    description: str
    permission: PermissionLevel = PermissionLevel.READ_ONLY
    confirmation_message: str = ""
    examples: list[str] = Field(default_factory=list)
    settings_schema: list[SkillSettingField] = Field(default_factory=list)


class FollowUpAction(BaseModel):
    """One-time action that still requires an explicit user confirmation."""

    skill_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class SkillResult(BaseModel):
    success: bool
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    follow_up: FollowUpAction | None = None


class AgentReply(BaseModel):
    text: str
    intent: str = "conversation"
    state: str = "idle"
    needs_confirmation: bool = False
    data: dict[str, Any] = Field(default_factory=dict)


class PendingAction(BaseModel):
    skill_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)
