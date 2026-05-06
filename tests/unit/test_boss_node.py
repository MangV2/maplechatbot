"""보스 추천 노드 단위 테스트."""
import pytest

from app.agent.nodes.boss_node import boss_node
from app.agent.state import AgentState


def test_boss_node_no_snapshot():
    """스냅샷 없으면 동기화 안내."""
    state: AgentState = {"query": "어떤 보스 도전 가능?", "character_snapshot": None}
    out = boss_node(state)
    assert "final_answer" in out
    assert "동기화" in out["final_answer"] or "캐릭터" in out["final_answer"]


def test_boss_node_with_combat_power():
    """전투력 있으면 도전 가능/다음 목표 보스 안내 + 마무리 멘트."""
    state: AgentState = {
        "query": "보스 추천",
        "character_snapshot": {
            "basic": {"level": 210},
            "stat": {
                "final_stat": [
                    {"stat_name": "전투력", "stat_value": "5000000"},
                ]
            },
        },
    }
    out = boss_node(state)
    assert "final_answer" in out
    assert "5,000,000" in out["final_answer"] or "5000000" in out["final_answer"]
    assert "보스" in out["final_answer"]
    assert "환산주스텟" in out["final_answer"]
    assert "1억" in out["final_answer"]


def test_boss_node_with_level_no_combat_power():
    """레벨만 있고 전투력 없으면 전투력 조회 안내 + 마무리 멘트."""
    state: AgentState = {
        "query": "보스 추천",
        "character_snapshot": {"basic": {"level": 210}},
    }
    out = boss_node(state)
    assert "final_answer" in out
    assert "전투력" in out["final_answer"]
    assert "환산주스텟" in out["final_answer"]
