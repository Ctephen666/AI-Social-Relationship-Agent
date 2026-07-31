import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agent.graph import RelationshipAgent
from app.database.base import Base
from app.database.models import User
from app.memory.service import MemoryService


def test_agent_runs_from_analysis_to_suggestion() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    user = User(nickname="张三", relationship="大学同学", priority="high", tags=["游戏"])
    db.add(user)
    db.flush()
    MemoryService().remember_fact(db, user.id, "喜欢角色扮演游戏", category="interest")
    db.commit()

    result = asyncio.run(RelationshipAgent(db).assess({
        "user_id": user.id,
        "nickname": user.nickname,
        "relationship": user.relationship,
        "base_priority": "high",
        "tags": ["游戏"],
        "interaction_days": 10,
        "last_message": "之前聊到游戏进度",
    }))

    assert result["relationship_health"] == "stale"
    assert result["semantic_memories"] == ["喜欢角色扮演游戏"]
    assert result["priority"] == "high"
    assert "轻量" in result["strategy"]
    assert result["suggestion_content"]
