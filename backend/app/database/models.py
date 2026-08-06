from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship as orm_relationship

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

    interactions: Mapped[list[InteractionRecord]] = orm_relationship(back_populates="user", cascade="all, delete-orphan")
    memories: Mapped[list[Memory]] = orm_relationship(back_populates="user", cascade="all, delete-orphan")
    profile_memory: Mapped[ProfileMemory | None] = orm_relationship(back_populates="user", cascade="all, delete-orphan", uselist=False)
    episodic_memories: Mapped[list[EpisodicMemory]] = orm_relationship(back_populates="user", cascade="all, delete-orphan")
    semantic_memories: Mapped[list[SemanticMemory]] = orm_relationship(back_populates="user", cascade="all, delete-orphan")


class InteractionRecord(Base):
    __tablename__ = "interaction_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="observed")
    source: Mapped[str] = mapped_column(String(40), default="manual")
    user: Mapped[User] = orm_relationship(back_populates="interactions")


class Memory(Base):
    """Legacy memory table kept for existing API compatibility."""

    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    facts: Mapped[str] = mapped_column(Text)
    preferences: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user: Mapped[User] = orm_relationship(back_populates="memories")


class ProfileMemory(Base):
    """Stable person-level context: relationship, style and boundaries."""

    __tablename__ = "profile_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    communication_style: Mapped[str] = mapped_column(String(100), default="自然、轻松")
    boundaries: Mapped[str] = mapped_column(Text, default="")
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    user: Mapped[User] = orm_relationship(back_populates="profile_memory")


class EpisodicMemory(Base):
    """Time-bound events and conversation episodes."""

    __tablename__ = "episodic_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now, index=True)
    summary: Mapped[str] = mapped_column(Text)
    topic: Mapped[str] = mapped_column(String(120), default="")
    sentiment: Mapped[str] = mapped_column(String(30), default="neutral")
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    source: Mapped[str] = mapped_column(String(40), default="manual")
    user: Mapped[User] = orm_relationship(back_populates="episodic_memories")


class SemanticMemory(Base):
    """Durable facts inferred or confirmed from interactions."""

    __tablename__ = "semantic_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    fact: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(60), default="general")
    confidence: Mapped[float] = mapped_column(Float, default=0.8)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(40), default="manual")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    user: Mapped[User] = orm_relationship(back_populates="semantic_memories")


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

class SparkStatus(str, Enum):
    active = "active"
    gray = "gray"
    none = "none"


class DesktopSparkScan(Base):
    """One visual spark classification result for a chat row in a local desktop scan."""

    __tablename__ = "desktop_spark_scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    nickname: Mapped[str] = mapped_column(String(100), index=True)
    platform: Mapped[str] = mapped_column(String(40), default="douyin")
    spark_status: Mapped[SparkStatus] = mapped_column(SqlEnum(SparkStatus), default=SparkStatus.none)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    screenshot_path: Mapped[str] = mapped_column(String(500))
    chat_list_bounds: Mapped[list[int]] = mapped_column(JSON, default=list)
    spark_bounds: Mapped[list[int]] = mapped_column(JSON, default=list)
    ocr_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutboundMessageAudit(Base):
    """Immutable audit row for each attempted external chat write."""

    __tablename__ = "outbound_message_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(64), index=True)
    platform: Mapped[str] = mapped_column(String(40), default="douyin")
    nickname: Mapped[str] = mapped_column(String(100), index=True)
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
