from app.agent.state import AgentState
from app.llm.provider import LLMProvider


class MessageGenerator:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider or LLMProvider()

    async def generate(self, state: AgentState) -> AgentState:
        if not state.get("need_reminder"):
            return {"suggestion_content": "", "tone": "无需建议", "risk_level": "low"}
        topic = state.get("last_message") or (state.get("memories") or ["最近的近况"])[-1]
        fallback = f"最近想起你之前提到的「{topic[:30]}」，后来怎么样了？"
        response = await self.provider.complete(
            "你是谨慎、真诚的社交关系维护助手。只生成一句中文聊天草稿，不承诺、施压、索取隐私，也不冒充用户。",
            f"关系：{state.get('relationship')}；标签：{','.join(state.get('tags', []))}；最近话题：{topic}；策略：{state.get('strategy')}。生成一句自然、轻松、不机械的消息。",
        )
        content = (response or fallback).replace("\n", " ").strip()[:300]
        return {"suggestion_content": content, "tone": "自然、轻松", "risk_level": "low"}

