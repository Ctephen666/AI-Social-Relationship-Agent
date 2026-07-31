from __future__ import annotations

from sqlalchemy.orm import Session
from langgraph.graph import END, START, StateGraph

from app.agent.message_strategy import MessageStrategyPlanner
from app.agent.priority_planner import PriorityPlanner
from app.agent.relationship_analyzer import RelationshipAnalyzer
from app.agent.state import AgentState
from app.llm.generator import MessageGenerator
from app.memory.service import MemoryService


class RelationshipAgent:
    """Five-step Agent MVP with an explicit, inspectable LangGraph execution path.

    START (Input) -> Relationship Analyzer -> Memory Retrieval -> Priority Planner
    -> Message Strategy -> Suggestion Generator -> END
    """

    def __init__(self, db: Session, memory_service: MemoryService | None = None) -> None:
        self.db = db
        self.memory_service = memory_service or MemoryService()
        self.relationship_analyzer = RelationshipAnalyzer()
        self.priority_planner = PriorityPlanner()
        self.message_strategy = MessageStrategyPlanner()
        self.generator = MessageGenerator()

        graph = StateGraph(AgentState)
        graph.add_node("relationship_analyzer", self.relationship_analyzer.analyze)
        graph.add_node("memory_retrieval", self._retrieve_memory)
        graph.add_node("priority_planner", self.priority_planner.plan)
        graph.add_node("message_strategy", self.message_strategy.plan)
        graph.add_node("suggestion_generator", self.generator.generate)
        graph.add_edge(START, "relationship_analyzer")
        graph.add_edge("relationship_analyzer", "memory_retrieval")
        graph.add_edge("memory_retrieval", "priority_planner")
        graph.add_edge("priority_planner", "message_strategy")
        graph.add_edge("message_strategy", "suggestion_generator")
        graph.add_edge("suggestion_generator", END)
        self.graph = graph.compile()

    def _retrieve_memory(self, state: AgentState) -> AgentState:
        bundle = self.memory_service.retrieve(self.db, state["user_id"])
        return {
            "profile_memory": bundle.profile,
            "episodic_memories": bundle.episodes,
            "semantic_memories": bundle.semantic_facts,
            "memories": bundle.flat_context,
        }

    async def assess(self, state: AgentState) -> AgentState:
        return await self.graph.ainvoke(state)
