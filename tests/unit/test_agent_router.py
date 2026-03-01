"""라우터 에이전트 단위 테스트 (파서, route_query, LLM mock)."""
import importlib
import pytest
from unittest.mock import patch, MagicMock

from app.agent.router import (
    ROUTE_BOSS,
    ROUTE_CLARIFY,
    ROUTE_GROWTH,
    ROUTE_NEWBIE,
    ROUTE_NO_ANSWER,
    ROUTE_RAG,
    NO_ANSWER_MESSAGE,
    _parse_router_response,
    route_query,
    router_agent_node,
)
from app.agent.state import AgentState


def test_route_query_reads_state_route():
    """route_query는 state['route']를 그대로 반환."""
    assert route_query({"route": ROUTE_RAG}) == ROUTE_RAG
    assert route_query({"route": ROUTE_GROWTH}) == ROUTE_GROWTH
    assert route_query({"route": ROUTE_CLARIFY}) == ROUTE_CLARIFY
    assert route_query({"route": ROUTE_NO_ANSWER}) == ROUTE_NO_ANSWER


def test_route_query_empty_state_defaults_rag():
    """route 없으면 ROUTE_RAG."""
    assert route_query({}) == ROUTE_RAG


def test_parse_router_response():
    """LLM 응답 파싱: 점수 1~5, BEST 추출."""
    scores, best = _parse_router_response(
        "RAG: 2\nGROWTH: 4\nBOSS: 1\nNEWBIE: 2\nBEST: growth"
    )
    assert scores.get("rag") == 2
    assert scores.get("growth") == 4
    assert best == "growth"


def test_parse_router_response_clamps_scores():
    """6 이상은 5로, 0 이하는 1로."""
    scores, _ = _parse_router_response("RAG: 9\nGROWTH: 0\nBEST: rag")
    assert scores.get("rag") == 5
    assert scores.get("growth") == 1


def test_parse_router_response_invalid_best_uses_max():
    """BEST가 없거나 잘못되면 최고 점수 항목."""
    scores, best = _parse_router_response("RAG: 1\nGROWTH: 5\nBOSS: 2\nNEWBIE: 1")
    assert best == "growth"


def test_parse_router_response_best_none():
    """BEST: none 이면 no_answer."""
    _, best = _parse_router_response("RAG: 1\nGROWTH: 1\nBOSS: 1\nNEWBIE: 1\nBEST: none")
    assert best == ROUTE_NO_ANSWER


def test_router_agent_node_empty_query_returns_clarify():
    """빈 질문이면 route=clarify, final_answer 안내."""
    out = router_agent_node({"query": "   "})
    assert out["route"] == ROUTE_CLARIFY
    assert "final_answer" in out
    assert out.get("route_confidence") == 0


def test_router_agent_node_confidence_below_3_returns_clarify():
    """LLM이 모든 항목 3 미만이면 재질문."""
    router_mod = importlib.import_module("app.agent.router")
    with patch.object(router_mod, "OpenAIClient") as mock_cls:
        mock_ai = MagicMock()
        mock_ai.chat_completion.return_value = (
            "RAG: 2\nGROWTH: 2\nBOSS: 1\nNEWBIE: 2\nBEST: rag"
        )
        mock_cls.return_value = mock_ai
        out = router_agent_node({"query": "아무거나"})
    assert out["route"] == ROUTE_CLARIFY
    assert "final_answer" in out
    assert "어떤 작업" in out["final_answer"] or "도와드릴지" in out["final_answer"]


def test_router_agent_node_confidence_3_or_more_returns_best_route():
    """LLM이 3 이상인 항목 있으면 해당 route만 반환 (final_answer 없음)."""
    router_mod = importlib.import_module("app.agent.router")
    with patch.object(router_mod, "OpenAIClient") as mock_cls:
        mock_ai = MagicMock()
        mock_ai.chat_completion.return_value = (
            "RAG: 5\nGROWTH: 1\nBOSS: 1\nNEWBIE: 1\nBEST: rag"
        )
        mock_cls.return_value = mock_ai
        out = router_agent_node({"query": "히어로 스킬 추천"})
    assert out["route"] == ROUTE_RAG
    assert out.get("route_confidence") == 5
    assert "final_answer" not in out


def test_router_agent_node_best_none_returns_no_answer():
    """LLM이 BEST: none 이면 적합한 에이전트 없음 메시지."""
    router_mod = importlib.import_module("app.agent.router")
    with patch.object(router_mod, "OpenAIClient") as mock_cls:
        mock_ai = MagicMock()
        mock_ai.chat_completion.return_value = (
            "RAG: 1\nGROWTH: 1\nBOSS: 1\nNEWBIE: 1\nBEST: none"
        )
        mock_cls.return_value = mock_ai
        out = router_agent_node({"query": "오늘 날씨 어때?"})
    assert out["route"] == ROUTE_NO_ANSWER
    assert out["final_answer"] == NO_ANSWER_MESSAGE