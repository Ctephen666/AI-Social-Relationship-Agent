from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database.base import Base
from app.database.models import ProfileMemory, User
from app.memory.service import MemoryService


def test_memory_service_retrieves_three_layers() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    user = User(nickname="张三", relationship="大学同学")
    session.add(user)
    session.flush()
    service = MemoryService()
    service.upsert_profile(session, user.id, "大学室友，喜欢 RPG", "轻松随意", "避免催问工作")
    service.record_episode(session, user.id, "聊到最近在玩艾尔登法环", topic="游戏", occurred_at=datetime.now() - timedelta(days=2))
    service.remember_fact(session, user.id, "喜欢角色扮演游戏", category="interest")
    session.commit()

    bundle = service.retrieve(session, user.id)

    assert bundle.profile["summary"] == "大学室友，喜欢 RPG"
    assert "艾尔登法环" in bundle.episodes[0]
    assert bundle.semantic_facts == ["喜欢角色扮演游戏"]
    assert len(bundle.flat_context) == 5
