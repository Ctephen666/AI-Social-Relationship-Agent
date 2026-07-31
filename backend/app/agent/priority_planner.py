from app.agent.state import AgentState


class PriorityPlanner:
    """Converts relationship health into transparent reminder priority."""

    def plan(self, state: AgentState) -> AgentState:
        base = state.get("base_priority", "medium")
        health = state.get("relationship_health", "healthy")
        days = int(state.get("interaction_days", 0))
        if health == "healthy":
            return {
                "priority": "low",
                "recommended_time": "暂不需要主动联系",
                "reason": f"距最近互动 {days} 天，仍在合理互动周期内。",
            }
        priority = "high" if base == "high" or health == "stale" else "medium"
        return {
            "priority": priority,
            "recommended_time": "今日 19:00–21:00",
            "reason": f"距最近互动 {days} 天，关系状态为 {health}；建议以低压力方式重新建立连接。",
        }
