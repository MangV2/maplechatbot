"""에이전트 그래프 통합 테스트 (라우터·RAG mock)."""
import importlib
import pytest
from unittest.mock import patch, MagicMock

from app.agent.graph import build_graph, invoke, reset_graph


def _rag_node_module():
    return importlib.import_module("app.agent.nodes.rag_node")


def _mock_router_rag(state):
    """라우터 mock: 항상 rag, confidence 5."""
    return {"route": "rag", "route_confidence": 5}


def _mock_router_boss(state):
    return {"route": "boss", "route_confidence": 5}


def _mock_router_clarify(state):
    return {"route": "clarify", "route_confidence": 0, "final_answer": "질문을 구체적으로 적어 주세요.", "references": []}


def _mock_router_no_answer(state):
    return {"route": "no_answer", "route_confidence": 0, "final_answer": "질문하신 내용에 답할 정확한 정보가 없습니다.", "references": []}


def _mock_router_character_sync(state):
    return {"route": "character_sync", "route_confidence": 5}


@pytest.fixture
def mock_rag():
    """get_rag().generate_answer mock."""
    rag = MagicMock()
    rag.generate_answer.return_value = {
        "answer": "테스트 RAG 답변입니다.",
        "references": [
            {"직업": "히어로", "직업군": "전사", "제목": "가이드", "작성일": "", "similarity_score": 0.9, "본문_요약": ""},
        ],
    }
    with patch.object(_rag_node_module(), "get_rag", return_value=rag):
        yield rag


def test_build_graph_compiles():
    """그래프 빌드 후 compile() 가능."""
    builder = build_graph()
    compiled = builder.compile()
    assert compiled is not None


def test_invoke_returns_answer_and_references(mock_rag):
    """라우터 mock으로 rag 분기 → RAG 답변 반환."""
    reset_graph()
    with patch("app.agent.graph.router_agent_node", side_effect=_mock_router_rag):
        result = invoke(query="히어로 스킬 추천", main_character_name=None)
    assert "answer" in result
    assert "references" in result
    assert result["answer"] == "테스트 RAG 답변입니다."
    assert len(result["references"]) == 1
    assert result["references"][0].get("직업") == "히어로"
    mock_rag.generate_answer.assert_called_once()


def test_invoke_empty_query_returns_graceful():
    """빈 질문이면 라우터가 clarify → 재질문 안내 반환."""
    reset_graph()
    result = invoke(query="   ", main_character_name=None)
    assert "answer" in result
    assert "질문을 입력" in result["answer"] or "구체적" in result["answer"]
    assert result["references"] == []


def test_invoke_boss_route_with_snapshot():
    """라우터 mock으로 boss 분기 + 스냅샷 전투력 → boss 노드 실행."""
    reset_graph()
    with patch("app.agent.graph.router_agent_node", side_effect=_mock_router_boss):
        result = invoke(
            query="어떤 보스 도전 가능?",
            character_snapshot={
                "basic": {"level": 210},
                "stat": {"final_stat": [{"stat_name": "전투력", "stat_value": "5000000"}]},
            },
        )
    assert "answer" in result
    assert "보스" in result["answer"]
    assert "전투력" in result["answer"] or "5,000,000" in result["answer"]


def test_invoke_clarify_route_returns_clarify_message():
    """라우터가 clarify 반환 시 재질문 메시지 그대로 반환."""
    reset_graph()
    with patch("app.agent.graph.router_agent_node", side_effect=_mock_router_clarify):
        result = invoke(query="애매한질문", main_character_name=None)
    assert result["answer"] == "질문을 구체적으로 적어 주세요."
    assert result["references"] == []


def test_invoke_no_answer_route_returns_no_answer_message():
    """라우터가 no_answer 반환 시 정확한 정보 없음 메시지 반환."""
    reset_graph()
    with patch("app.agent.graph.router_agent_node", side_effect=_mock_router_no_answer):
        result = invoke(query="오늘 날씨 어때?", main_character_name=None)
    assert result["answer"] == "질문하신 내용에 답할 정확한 정보가 없습니다."
    assert result["references"] == []


def test_invoke_character_sync_route_returns_pending_when_name_extracted():
    """라우터가 character_sync 반환 + 캐릭터명 추출 시 확인 문구 + pending_character_sync."""
    reset_graph()
    with patch("app.agent.graph.router_agent_node", side_effect=_mock_router_character_sync):
        result = invoke(
            query="루나스톤 정보 불러와줘",
            user_id="user-1",
        )
    assert "동기화 진행" in result["answer"]
    assert result.get("pending_character_sync") == "루나스톤"
