from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Priority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class SuggestionStatus(str, Enum):
    pending = "pending"
    copied = "copied"
    dismissed = "dismissed"
    used = "used"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nickname: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    relationship: Mapped[str] = mapped_column(String(100), default="朋友")
    priority: Mapped[Priority] = mapped_column(SqlEnum(Priority), default=Priority.medium)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    interactions: Mapped[list[InteractionRecord]] = relationship(back_populates="user", cascade="all, delete-orphan")
    memories: Mapped[list[Memory]] = relationship(back_populates="user", cascade="all, delete-orphan")


class InteractionRecord(Base):
    __tablename__ = "interaction_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="observed")
    source: Mapped[str] = mapped_column(String(40), default="manual")
    user: Mapped[User] = relationship(back_populates="interactions")


class Memory(Base):
    __tablename__ = "memories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    facts: Mapped[str] = mapped_column(Text)
    preferences: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user: Mapped[User] = relationship(back_populates="memories")


class RelationshipAssessment(Base):
    __tablename__ = "relationship_assessments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    need_reminder: Mapped[bool]
    priority: Mapped[Priority] = mapped_column(SqlEnum(Priority))
    recommended_time: Mapped[str] = mapped_column(String(100))
    strategy: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MessageSuggestion(Base):
    __tablename__ = "message_suggestions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    assessment_id: Mapped[int | None] = mapped_column(ForeignKey("relationship_assessments.id"), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    tone: Mapped[str] = mapped_column(String(100))
    reason: Mapped[str] = mapped_column(Text)
    risk_level: Mapped[str] = mapped_column(String(20), default="low")
    status: Mapped[SuggestionStatus] = mapped_column(SqlEnum(SuggestionStatus), default=SuggestionStatus.pending)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScanTask(Base):
    __tablename__ = "scan_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    source: Mapped[str] = mapped_column(String(40), default="scheduler")
    screenshot_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AppSetting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

