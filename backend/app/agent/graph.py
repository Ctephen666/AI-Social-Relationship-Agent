from langgraph.graph import END, START, StateGraph

from app.agent.evaluator import RelationshipEvaluator
from app.agent.planner import RelationshipPlanner
from app.agent.state import AgentState
from app.llm.generator import MessageGenerator


class RelationshipAgent:
    """LangGraph 编排：规则评估 -> 策略规划 -> 异步话术生成。"""

    def __init__(self) -> None:
        self.evaluator = RelationshipEvaluator()
        self.planner = RelationshipPlanner()
        self.generator = MessageGenerator()
        graph = StateGraph(AgentState)
        graph.add_node("evaluate", self.evaluator.evaluate)
        graph.add_node("plan", self.planner.plan)
        graph.add_node("generate", self.generator.generate)
        graph.add_edge(START, "evaluate")
        graph.add_edge("evaluate", "plan")
        graph.add_edge("plan", "generate")
        graph.add_edge("generate", END)
        self.graph = graph.compile()

    async def assess(self, state: AgentState) -> AgentState:
        return await self.graph.ainvoke(state)

