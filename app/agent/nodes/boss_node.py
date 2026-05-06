"""보스 추천 노드: OpenAI Function Calling으로 보스 테이블 + 커뮤니티 팁 통합 답변."""
import logging
from typing import Any

from app.agent.snapshot_utils import get_combat_power_from_snapshot, get_level_from_snapshot
from app.agent.state import AgentState
from app.agent.tools.boss_tools import BOSS_TOOLS, make_boss_tool_executor
from app.rag.loader import get_rag
from app.rag.openai_client import OpenAIClient

logger = logging.getLogger(__name__)

BOSS_SYSTEM = """당신은 메이플스토리 보스 전문 어드바이저입니다.
제공된 도구를 활용해 캐릭터 스펙에 맞는 보스 추천과 공략 팁을 제공하세요.

사용 가능한 도구:
- lookup_boss_table: 전투력 기준 도전 가능 보스 조회 (권장 전투력 표 기반)
- search_boss_tips: 커뮤니티 보스 공략·팁 검색

답변 규칙:
1. 전투력 정보가 있으면 반드시 lookup_boss_table을 먼저 호출하세요.
2. 특정 보스 공략이나 팁을 묻는다면 search_boss_tips도 호출하세요.
3. 최종 답변은 한국어로, 도전 가능 보스·지금 도전해볼 만한 보스·다음 목표 순으로 정리하세요.
4. 전투력 1억 이상 구간은 실제 딜링과 차이가 있을 수 있어 환산주스텟 확인을 권장하세요."""


def boss_node(state: AgentState) -> dict[str, Any]:
    """Function Calling으로 보스 테이블 조회 + 커뮤니티 팁 검색 후 종합 답변 생성."""
    query = state.get("query", "")
    snapshot = state.get("character_snapshot")
    level = get_level_from_snapshot(snapshot)
    combat_power = get_combat_power_from_snapshot(snapshot)
    main_char = state.get("main_character_name")

    if level is None or level < 1:
        return {
            "final_answer": (
                "캐릭터 정보가 없습니다. 본캐를 등록한 뒤 **캐릭터 동기화**를 실행해 주세요. "
                "그러면 전투력 기준으로 도전 가능한 보스를 안내해 드립니다."
            ),
            "references": [],
        }

    rag = get_rag()
    executor = make_boss_tool_executor(
        combat_power=combat_power,
        rag_search_fn=lambda q, k=3: rag.search(q, top_k=k),
    )

    char_info_parts = []
    if main_char:
        char_info_parts.append(f"캐릭터: {main_char}")
    if combat_power is not None:
        char_info_parts.append(f"전투력: {combat_power:,}")
    else:
        char_info_parts.append("전투력: 정보 없음")
    if level:
        char_info_parts.append(f"레벨: {level}")
    char_info = ", ".join(char_info_parts)

    messages = [
        {"role": "system", "content": BOSS_SYSTEM},
        {
            "role": "user",
            "content": f"[캐릭터 정보]\n{char_info}\n\n[질문]\n{query}",
        },
    ]

    try:
        ai = OpenAIClient()
        answer = ai.chat_with_tools(
            messages=messages,
            tools=BOSS_TOOLS,
            tool_executor=executor,
        )
        return {"final_answer": answer or "보스 추천 정보를 생성할 수 없습니다.", "references": []}
    except Exception as e:
        logger.exception("보스 노드 Function Calling 실패: %s", e)
        return {
            "final_answer": "보스 추천 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
            "references": [],
        }
