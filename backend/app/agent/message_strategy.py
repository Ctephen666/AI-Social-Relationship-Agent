from app.agent.state import AgentState


class MessageStrategyPlanner:
    """Turns relationship and memory context into an explicit, safe communication strategy."""

    def plan(self, state: AgentState) -> AgentState:
        if not state.get("need_reminder"):
            return {"strategy": "保持自然节奏，等待对方动态或合适话题。"}
        episodes = state.get("episodic_memories", [])
        facts = state.get("semantic_memories", [])
        topic = state.get("last_message") or (episodes[-1] if episodes else "") or (facts[0] if facts else "近况")
        profile = state.get("profile_memory", {})
        tone = profile.get("communication_style") or "自然、轻松"
        boundaries = profile.get("boundaries")
        boundary_note = f"；避免触及：{boundaries}" if boundaries else ""
        return {
            "strategy": f"使用{tone}语气，以“{topic[:60]}”为切入点，提出一个容易回答的轻量问题{boundary_note}。"
        }
