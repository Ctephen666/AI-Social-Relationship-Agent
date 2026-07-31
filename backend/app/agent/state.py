from typing import TypedDict


class AgentState(TypedDict, total=False):
    """State exchanged by the five-node social relationship LangGraph."""

    user_id: int
    nickname: str
    relationship: str
    base_priority: str
    tags: list[str]
    interaction_days: int
    last_message: str

    relationship_health: str
    relationship_score: int
    need_reminder: bool
    priority: str
    recommended_time: str
    strategy: str
    reason: str

    profile_memory: dict[str, str]
    episodic_memories: list[str]
    semantic_memories: list[str]
    memories: list[str]

    suggestion_content: str
    tone: str
    risk_level: str
