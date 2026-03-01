"""성장 방향 노드 단위 테스트."""
import importlib
import pytest
from unittest.mock import patch, MagicMock

from app.agent.nodes.growth_node import growth_node
from app.agent.state import AgentState


def test_growth_node_no_snapshot():
    """스냅샷 없으면 동기화 안내."""
    state: AgentState = {"query": "다음에 뭘 올려?", "character_snapshot": None}
    out = growth_node(state)
    assert "final_answer" in out
    assert "동기화" in out["final_answer"] or "캐릭터" in out["final_answer"]
    assert out.get("references") == []


def test_growth_node_with_snapshot_mock_openai():
    """스냅샷 있으면 GPT 호출 후 우선순위 형식 답변."""
    state: AgentState = {
        "query": "성장 우선순위",
        "character_snapshot": {"basic": {"level": 200, "character_class": "히어로"}, "stat": {}, "item_equipment": {}},
    }
    growth_mod = importlib.import_module("app.agent.nodes.growth_node")
    with patch.object(growth_mod, "OpenAIClient") as mock_cls:
        mock_ai = MagicMock()
        mock_ai.chat_completion.return_value = "1. 장비 스타포스 2. 코어 강화 3. 유니온"
        mock_cls.return_value = mock_ai
        out = growth_node(state)
    assert "final_answer" in out
    assert "1." in out["final_answer"] or "장비" in out["final_answer"]
    mock_ai.chat_completion.assert_called_once()
