"""캐릭터 동기화 요청 노드 단위 테스트."""
import pytest
from unittest.mock import patch, MagicMock

from app.agent.nodes.character_sync_node import character_sync_node
from app.agent.state import AgentState


def test_character_sync_node_no_user_id():
    """로그인 없으면 로그인 안내."""
    state: AgentState = {
        "query": "루나스톤 정보 불러와줘",
        "user_id": None,
    }
    out = character_sync_node(state)
    assert "로그인" in out["final_answer"]
    assert out.get("pending_character_sync") is None


def test_character_sync_node_with_name_extracted():
    """캐릭터명 추출되면 확인 문구 + pending_character_sync."""
    state: AgentState = {
        "query": "루나스톤 정보 불러와줘",
        "user_id": "user-1",
    }
    out = character_sync_node(state)
    assert "루나스톤" in out["final_answer"]
    assert "동기화 진행" in out["final_answer"]
    assert out.get("pending_character_sync") == "루나스톤"


def test_character_sync_node_no_name_asks_for_name():
    """캐릭터명 없으면 캐릭터명 요청."""
    state: AgentState = {
        "query": "캐릭터 정보 불러오기 해줘",
        "user_id": "user-1",
    }
    with patch("app.agent.nodes.character_sync_node.OpenAIClient") as mock_cls:
        mock_ai = MagicMock()
        mock_ai.chat_completion.return_value = ""
        mock_cls.return_value = mock_ai
        out = character_sync_node(state)
    assert "캐릭터명" in out["final_answer"] or "어떤 캐릭터" in out["final_answer"]
    assert out.get("pending_character_sync") is None
