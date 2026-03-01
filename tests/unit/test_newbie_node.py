"""뉴비 가이드 노드 단위 테스트."""
import pytest
from unittest.mock import patch

from app.agent.nodes.newbie_node import newbie_node
from app.agent.state import AgentState


def test_newbie_node_returns_guide():
    """고정 가이드 문단 포함."""
    state: AgentState = {"query": "뉴비 가이드"}
    out = newbie_node(state)
    assert "final_answer" in out
    assert "내실" in out["final_answer"] or "링크" in out["final_answer"] or "유니온" in out["final_answer"]


def test_newbie_node_with_level_appends_level():
    """스냅샷에 레벨 있으면 현재 레벨 문구 추가."""
    state: AgentState = {
        "query": "초보 가이드",
        "character_snapshot": {"basic": {"level": 100}},
    }
    out = newbie_node(state)
    assert "100" in out["final_answer"]
