"""LangGraph 에이전트 그래프: 라우터(LLM) → clarify | RAG | growth | boss | newbie."""
import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agent.router import route_query, router_agent_node
from app.agent.state import AgentState
from app.agent.nodes.rag_node import rag_node
from app.agent.nodes.growth_node import growth_node
from app.agent.nodes.boss_node import boss_node
from app.agent.nodes.newbie_node import newbie_node
from app.agent.nodes.character_sync_node import character_sync_node

logger = logging.getLogger(__name__)


def _clarify_node(state: AgentState) -> dict[str, Any]:
    """재질문 시: 라우터가 이미 final_answer를 넣어 둠, 통과만."""
    return {}


def _no_answer_node(state: AgentState) -> dict[str, Any]:
    """적합한 에이전트 없음: 라우터가 이미 final_answer 넣어 둠, 통과만."""
    return {}


def build_graph() -> StateGraph:
    """StateGraph: START → router(LLM 분류) → (clarify|no_answer|rag|growth|boss|newbie) → END."""
    builder = StateGraph(AgentState)
    builder.add_node("router", router_agent_node)
    builder.add_node("clarify", _clarify_node)
    builder.add_node("no_answer", _no_answer_node)
    builder.add_node("rag", rag_node)
    builder.add_node("growth", growth_node)
    builder.add_node("boss", boss_node)
    builder.add_node("newbie", newbie_node)
    builder.add_node("character_sync", character_sync_node)
    builder.add_edge(START, "router")
    builder.add_conditional_edges(
        "router",
        route_query,
        {
            "clarify": "clarify",
            "no_answer": "no_answer",
            "rag": "rag",
            "growth": "growth",
            "boss": "boss",
            "newbie": "newbie",
            "character_sync": "character_sync",
        },
    )
    builder.add_edge("clarify", END)
    builder.add_edge("no_answer", END)
    builder.add_edge("rag", END)
    builder.add_edge("growth", END)
    builder.add_edge("boss", END)
    builder.add_edge("newbie", END)
    builder.add_edge("character_sync", END)
    return builder


def get_graph():
    """컴파일된 그래프 싱글톤."""
    if get_graph._compiled is None:
        get_graph._compiled = build_graph().compile()
    return get_graph._compiled


def reset_graph():
    """테스트 또는 그래프 변경 시 싱글톤 초기화."""
    get_graph._compiled = None


get_graph._compiled = None


def invoke(
    query: str,
    main_character_name: str | None = None,
    user_id: str | None = None,
    character_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """그래프 1회 실행 후 최종 상태 반환."""
    initial: AgentState = {
        "query": query,
        "main_character_name": main_character_name,
        "user_id": user_id,
        "character_snapshot": character_snapshot,
    }
    graph = get_graph()
    final = graph.invoke(initial)
    return {
        "answer": final.get("final_answer", ""),
        "references": final.get("references", []),
        "pending_character_sync": final.get("pending_character_sync"),
    }
