from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import EpisodicMemory, Memory, ProfileMemory, SemanticMemory


@dataclass(frozen=True)
class MemoryBundle:
    """Bounded three-layer context supplied to an Agent run."""

    profile: dict[str, str] = field(default_factory=dict)
    episodes: list[str] = field(default_factory=list)
    semantic_facts: list[str] = field(default_factory=list)

    @property
    def flat_context(self) -> list[str]:
        profile = [f"档案：{key}={value}" for key, value in self.profile.items() if value]
        return profile + [f"事件：{value}" for value in self.episodes] + [f"事实：{value}" for value in self.semantic_facts]


class MemoryService:
    """Repository and retrieval policy for profile, episodic and semantic memory."""

    def retrieve(self, db: Session, user_id: int, episode_limit: int = 4, semantic_limit: int = 6) -> MemoryBundle:
        profile = db.scalar(select(ProfileMemory).where(ProfileMemory.user_id == user_id))
        episodes = list(db.scalars(
            select(EpisodicMemory)
            .where(EpisodicMemory.user_id == user_id)
            .order_by(EpisodicMemory.occurred_at.desc(), EpisodicMemory.importance.desc())
            .limit(episode_limit)
        ).all())
        facts = list(db.scalars(
            select(SemanticMemory)
            .where(SemanticMemory.user_id == user_id, SemanticMemory.is_active.is_(True))
            .order_by(SemanticMemory.confidence.desc(), SemanticMemory.updated_at.desc())
            .limit(semantic_limit)
        ).all())
        legacy = list(db.scalars(
            select(Memory).where(Memory.user_id == user_id).order_by(Memory.created_at.desc()).limit(2)
        ).all())
        profile_data = {
            "summary": profile.summary if profile else "",
            "communication_style": profile.communication_style if profile else "",
            "boundaries": profile.boundaries if profile else "",
        }
        episode_text = [self._episode_text(item) for item in reversed(episodes)]
        semantic_text = [item.fact for item in facts]
        semantic_text.extend(f"{item.facts} {item.preferences}".strip() for item in legacy)
        return MemoryBundle(profile=profile_data, episodes=episode_text, semantic_facts=semantic_text)

    def upsert_profile(
        self,
        db: Session,
        user_id: int,
        summary: str,
        communication_style: str = "自然、轻松",
        boundaries: str = "",
        preferences: dict | None = None,
    ) -> ProfileMemory:
        profile = db.scalar(select(ProfileMemory).where(ProfileMemory.user_id == user_id))
        if profile is None:
            profile = ProfileMemory(user_id=user_id)
            db.add(profile)
        profile.summary = summary
        profile.communication_style = communication_style
        profile.boundaries = boundaries
        profile.preferences = preferences or {}
        db.flush()
        return profile

    def record_episode(
        self,
        db: Session,
        user_id: int,
        summary: str,
        topic: str = "",
        sentiment: str = "neutral",
        importance: float = 0.5,
        source: str = "agent",
        occurred_at: datetime | None = None,
    ) -> EpisodicMemory:
        episode = EpisodicMemory(
            user_id=user_id,
            summary=summary,
            topic=topic,
            sentiment=sentiment,
            importance=max(0.0, min(1.0, importance)),
            source=source,
            occurred_at=occurred_at or datetime.now(),
        )
        db.add(episode)
        db.flush()
        return episode

    def remember_fact(
        self,
        db: Session,
        user_id: int,
        fact: str,
        category: str = "general",
        confidence: float = 0.8,
        source: str = "agent",
    ) -> SemanticMemory:
        item = SemanticMemory(
            user_id=user_id,
            fact=fact,
            category=category,
            confidence=max(0.0, min(1.0, confidence)),
            source=source,
        )
        db.add(item)
        db.flush()
        return item

    @staticmethod
    def _episode_text(item: EpisodicMemory) -> str:
        prefix = f"{item.occurred_at:%Y-%m-%d}"
        topic = f"（{item.topic}）" if item.topic else ""
        return f"{prefix}{topic}：{item.summary}"
