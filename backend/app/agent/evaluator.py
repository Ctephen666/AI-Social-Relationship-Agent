from datetime import datetime

from app.agent.state import AgentState


class RelationshipEvaluator:
    """确定性规则先行：结果可解释，LLM 不单独决定提醒。"""

    thresholds = {"high": 3, "medium": 7, "low": 14}

    def evaluate(self, state: AgentState) -> AgentState:
        priority = state.get("base_priority", "medium")
        days = max(0, int(state.get("interaction_days", 0)))
        threshold = self.thresholds.get(priority, 7)
        need_reminder = days >= threshold
        if priority == "high" and days >= threshold * 2:
            evaluated_priority = "high"
        elif need_reminder:
            evaluated_priority = priority
        else:
            evaluated_priority = "low"
        return {"need_reminder": need_reminder, "priority": evaluated_priority}

