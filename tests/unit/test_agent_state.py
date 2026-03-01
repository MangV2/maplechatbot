"""에이전트 상태(TypedDict) 단위 테스트."""
import pytest

from app.agent.state import AgentState


def test_agent_state_can_hold_query_and_answer():
    """AgentState에 query, final_answer 등 필드 설정 가능."""
    state: AgentState = {
        "query": "테스트 질문",
        "final_answer": "테스트 답변",
        "references": [],
    }
    assert state["query"] == "테스트 질문"
    assert state["final_answer"] == "테스트 답변"
    assert state["references"] == []


def test_agent_state_optional_fields():
    """선택 필드 없이 최소만 넣어도 유효."""
    state: AgentState = {"query": "만"}
    assert state.get("main_character_name") is None
    assert state.get("character_snapshot") is None
