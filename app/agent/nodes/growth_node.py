"""성장 방향성 스킬 노드: 스냅샷 기반 다음 단계·우선순위 제안."""
import logging
from typing import Any

from app.agent.snapshot_utils import snapshot_summary
from app.agent.state import AgentState
from app.rag.openai_client import OpenAIClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """당신은 메이플스토리 성장 조언 AI입니다.
캐릭터 현재 스펙(레벨, 직업, 스탯, 장비 요약)을 보고, 다음에 할 일 우선순위와 체크리스트를 3~5개 항목으로 간단히 제시하세요.
장비 강화, 스킬 코어, 링크/유니온, 보스 도전 순서 등 구체적으로 적어주세요."""


def growth_node(state: AgentState) -> dict[str, Any]:
    """스냅샷 요약 + GPT로 성장 우선순위·체크리스트 생성."""
    query = (state.get("query") or "").strip()
    snapshot = state.get("character_snapshot")

    summary = snapshot_summary(snapshot)
    if not summary:
        return {
            "final_answer": "캐릭터 정보가 없습니다. 본캐를 등록한 뒤 **캐릭터 동기화**를 실행해 주세요. (마이페이지에서 sync 버튼)",
            "references": [],
        }

    user_content = f"""<현재 캐릭터 스펙>
{summary}

<질문>
{query or '다음에 뭘 올려야 할지 우선순위 알려줘'}

위 스펙을 바탕으로 성장 우선순위와 체크리스트를 알려주세요."""

    try:
        ai = OpenAIClient()
        answer = ai.chat_completion(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
        )
        return {"final_answer": answer or "답변을 생성하지 못했습니다.", "references": []}
    except Exception as e:
        logger.exception("growth_node OpenAI 호출 실패: %s", e)
        return {
            "final_answer": "성장 방향 조언을 생성하는 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
            "references": [],
        }
