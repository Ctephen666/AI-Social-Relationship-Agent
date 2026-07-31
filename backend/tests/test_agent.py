import asyncio

from app.agent.graph import RelationshipAgent


def test_high_priority_stale_contact_requires_reminder() -> None:
    result = asyncio.run(RelationshipAgent().assess({
        "user_id": 1,
        "nickname": "张三",
        "relationship": "大学同学",
        "base_priority": "high",
        "tags": ["游戏"],
        "interaction_days": 10,
        "last_message": "聊游戏",
        "memories": [],
    }))
    assert result["need_reminder"] is True
    assert result["priority"] == "high"
    assert result["suggestion_content"]

