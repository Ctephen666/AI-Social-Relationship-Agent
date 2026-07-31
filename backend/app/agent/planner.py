from app.agent.state import AgentState


class RelationshipPlanner:
    def plan(self, state: AgentState) -> AgentState:
        days = int(state.get("interaction_days", 0))
        relationship = state.get("relationship", "朋友")
        last_message = state.get("last_message", "")
        memories = state.get("memories", [])
        topic = last_message or (memories[-1] if memories else "近况")
        if not state.get("need_reminder"):
            return {
                "recommended_time": "暂不需要主动联系",
                "strategy": "保持自然节奏，等待合适的话题或对方的新动态。",
                "reason": f"距最近互动 {days} 天，仍处于该关系的合理互动周期内。",
            }
        strategy = f"以「{topic[:50]}」为切入点，采用轻量、可自然结束的问候。"
        return {
            "recommended_time": "今日 19:00–21:00",
            "strategy": strategy,
            "reason": f"{relationship}关系已 {days} 天未见互动，超过当前维护阈值；建议以已有话题自然续聊。",
        }

