from app.agent.state import AgentState


class RelationshipAnalyzer:
    """Deterministic relationship-health calculation before any LLM call."""

    _thresholds = {"high": 3, "medium": 7, "low": 14}

    def analyze(self, state: AgentState) -> AgentState:
        base_priority = state.get("base_priority", "medium")
        gap = max(0, int(state.get("interaction_days", 0)))
        threshold = self._thresholds.get(base_priority, 7)
        score = min(100, round(gap / threshold * 50) + (30 if base_priority == "high" else 15 if base_priority == "medium" else 0))
        if gap >= threshold * 2:
            health = "stale"
        elif gap >= threshold:
            health = "needs_attention"
        else:
            health = "healthy"
        return {
            "relationship_score": score,
            "relationship_health": health,
            "need_reminder": health != "healthy",
        }
