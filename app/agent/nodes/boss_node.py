"""보스 추천 노드: 전투력 기준 도전 가능 보스 안내 (권장 전투력 표 참고)."""
import logging
from typing import Any

from app.agent.data.boss_specs import COMBAT_POWER_100M, get_doable_bosses
from app.agent.snapshot_utils import get_combat_power_from_snapshot, get_level_from_snapshot
from app.agent.state import AgentState

logger = logging.getLogger(__name__)

CLOSING_NOTE = (
    "**전투력 1억 이상** 구간은 실제 딜링과 차이가 클 수 있어, "
    "**환산주스텟 사이트**를 이용해 정확한 보스 배율을 확인해 주세요."
)


def boss_node(state: AgentState) -> dict[str, Any]:
    """스냅샷 전투력 + 보스 권장 전투력 표로 도전 가능/다음 목표 보스 안내."""
    snapshot = state.get("character_snapshot")
    level = get_level_from_snapshot(snapshot)
    combat_power = get_combat_power_from_snapshot(snapshot)

    if level is None or level < 1:
        return {
            "final_answer": "캐릭터 정보가 없습니다. 본캐를 등록한 뒤 **캐릭터 동기화**를 실행해 주세요. 그러면 전투력 기준으로 도전 가능한 보스를 안내해 드립니다.",
            "references": [],
        }

    doable, try_soon, next_goal = get_doable_bosses(combat_power)

    if combat_power is None:
        lines = [
            "전투력이 조회되지 않았습니다. (넥슨 API에서 전투력이 제공되는 경우에 한해 표시됩니다.)",
            "캐릭터 동기화 후 전투력이 조회되면, 전투력 기준으로 도전 가능 보스를 안내해 드립니다.",
        ]
    else:
        lines = [f"**현재 전투력 {combat_power:,}** 기준 보스 추천입니다.\n"]
        if doable:
            lines.append("**도전 여유 있는 보스**: " + ", ".join(doable[-5:]) + "\n")
        if try_soon:
            lines.append("**지금 도전해볼 만한 보스**: " + ", ".join(try_soon) + "\n")
        if next_goal:
            lines.append("**다음 목표 보스**: " + ", ".join(next_goal) + "\n")
        if not (doable or try_soon or next_goal):
            lines.append("아직 권장 전투력에 해당하는 보스가 없을 수 있습니다. 성장 후 다시 조회해 보세요.")

    lines.append("")
    lines.append(CLOSING_NOTE)

    return {"final_answer": "\n".join(lines).strip(), "references": []}
