from typing import TypedDict

from app.database.models import Priority


class AgentState(TypedDict, total=False):
    user_id: int
    nickname: str
    relationship: str
    base_priority: str
    tags: list[str]
    interaction_days: int
    last_message: str
    memories: list[str]
    need_reminder: bool
    priority: str
    recommended_time: str
    strategy: str
    reason: str
    suggestion_content: str
    tone: str
    risk_level: str

