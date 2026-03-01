"""뉴비 가이드 스킬 노드: 내실 체우기·성장 순서 안내."""
import logging
from typing import Any

from app.agent.snapshot_utils import get_level_from_snapshot
from app.agent.state import AgentState
from app.rag.loader import get_rag

logger = logging.getLogger(__name__)

NEWBIE_GUIDE = """
**뉴비·초보를 위한 메이플스토리 내실 체우기 가이드**

1. **레벨 1~100**: 메인 퀘스트와 사냥으로 레벨업. 직업별 1차~4차 전직 완료.
2. **링크 스킬**: 부캐를 키워 링크 스킬을 쌓으면 본캐가 강해집니다. (시그너스, 데몬어벤져 등)
3. **유니온**: 140레벨 캐릭터들이 모여 유니온 레벨을 올리면 스탯 보너스.
4. **스킬 코어·강화**: 5차 스킬 강화 코어, V매트릭스 강화.
5. **장비**: 에픽 이상 장비 → 스타포스 10~12 → 세트 효과 맞추기.
6. **보스**: 자쿰·혼테일부터 차례로 도전해 보스 장비와 메소를 확보하세요.

캐릭터를 동기화하면 현재 레벨에 맞는 구체적인 다음 단계도 안내해 드립니다.
""".strip()


def newbie_node(state: AgentState) -> dict[str, Any]:
    """고정 가이드 + (선택) RAG로 내실 체우기 보조."""
    query = (state.get("query") or "").strip()
    snapshot = state.get("character_snapshot")
    level = get_level_from_snapshot(snapshot)

    answer_parts = [NEWBIE_GUIDE]

    # RAG로 "내실 체우기" 관련 게시글 검색해 보조 문단 추가 (선택)
    if query and ("내실" in query or "초보" in query):
        try:
            rag = get_rag()
            result = rag.generate_answer(
                query="뉴비 내실 체우기 순서 초보 가이드",
                top_k=2,
                use_cot=False,
                main_character_name=state.get("main_character_name"),
            )
            if result.get("answer") and "찾을 수 없습니다" not in result.get("answer", ""):
                answer_parts.append("\n\n---\n**커뮤니티 참고**\n" + (result["answer"][:500] or ""))
        except Exception as e:
            logger.debug("newbie_node RAG 보조 실패 (무시): %s", e)

    if level is not None and level > 0:
        answer_parts.append(f"\n\n(현재 조회된 캐릭터 레벨: {level})")

    return {"final_answer": "\n".join(answer_parts), "references": []}
