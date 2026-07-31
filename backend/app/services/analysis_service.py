from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.graph import RelationshipAgent
from app.agent.state import AgentState
from app.database.models import MessageSuggestion, Priority, RelationshipAssessment, User
from app.memory.service import MemoryService


class AnalysisService:
    def __init__(self) -> None:
        self.agent = RelationshipAgent()
        self.memory = MemoryService()

    async def analyze_user(self, db: Session, user: User, interaction_days: int, last_message: str = "") -> MessageSuggestion | None:
        state: AgentState = {
            "user_id": user.id,
            "nickname": user.nickname,
            "relationship": user.relationship,
            "base_priority": user.priority.value,
            "tags": user.tags or [],
            "interaction_days": interaction_days,
            "last_message": last_message,
            "memories": self.memory.recent_context(db, user.id),
        }
        result = await self.agent.assess(state)
        assessment = RelationshipAssessment(
            user_id=user.id,
            need_reminder=bool(result["need_reminder"]),
            priority=Priority(result["priority"]),
            recommended_time=result["recommended_time"],
            strategy=result["strategy"],
            reason=result["reason"],
        )
        db.add(assessment)
        db.flush()
        if not result["need_reminder"] or not result.get("suggestion_content"):
            db.commit()
            return None
        suggestion = MessageSuggestion(
            user_id=user.id,
            assessment_id=assessment.id,
            content=result["suggestion_content"],
            tone=result["tone"],
            reason=result["reason"],
            risk_level=result["risk_level"],
        )
        db.add(suggestion)
        db.commit()
        db.refresh(suggestion)
        return suggestion

