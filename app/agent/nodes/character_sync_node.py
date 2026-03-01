"""캐릭터 동기화 요청 노드: 질문에서 캐릭터명 추출 후 허락받기 안내, pending_character_sync 설정."""
import logging
import re
from typing import Any

from app.agent.state import AgentState
from app.rag.openai_client import OpenAIClient

logger = logging.getLogger(__name__)

CONFIRM_INSTRUCTION = (
    "진행하시려면 채팅창에 **'동기화 진행'** 이라고 입력해 주세요. "
    "(로그인 상태에서만 가능합니다.)"
)
NO_NAME_MESSAGE = (
    "어떤 캐릭터의 정보를 불러올까요? "
    "캐릭터명을 포함해서 요청해 주세요. 예: **루나스톤** 정보 불러와줘"
)
NEED_LOGIN = "캐릭터 정보 불러오기는 **로그인** 후 이용할 수 있습니다. 로그인하고 다시 요청해 주세요."

EXTRACT_NAME_SYSTEM = """사용자가 메이플스토리 캐릭터 정보를 넥슨 API로 불러오려고 합니다.
질문에서 불러올 캐릭터의 닉네임(캐릭터명)만 추출하세요. 한글/영문/숫자만 가능합니다.
캐릭터명이 없으면 빈 문자열을 반환하세요. 다른 단어 없이 캐릭터명만 한 줄로 답하세요."""


def _extract_character_name(query: str) -> str | None:
    """LLM으로 질문에서 캐릭터명 추출. 없으면 None."""
    query = (query or "").strip()
    if not query:
        return None
    # 간단한 패턴: "OOO 정보 불러와줘", "OOO 동기화", "캐릭터 OOO"
    patterns = [
        r"(?:캐릭터\s+)?([가-힣a-zA-Z0-9]{2,20})\s*(?:정보\s*불러|동기화|정보\s*조회)",
        r"^([가-힣a-zA-Z0-9]{2,20})\s*(?:정보|동기화|정보\s*불러)",
        r"(?:정보\s*불러와줘|동기화\s*해줘)\s*[:\s]*([가-힣a-zA-Z0-9]{2,20})?",
    ]
    for pat in patterns:
        m = re.search(pat, query, re.IGNORECASE)
        if m and m.lastindex >= 1:
            name = (m.group(1) or "").strip()
            if name and name not in ("캐릭터", "정보", "동기화", "불러와줘", "조회"):
                return name
    try:
        ai = OpenAIClient()
        resp = ai.chat_completion(
            messages=[
                {"role": "system", "content": EXTRACT_NAME_SYSTEM},
                {"role": "user", "content": f"질문: {query}"},
            ],
            max_tokens=30,
            temperature=0,
        )
        name = (resp or "").strip()
        if name and re.match(r"^[가-힣a-zA-Z0-9]{2,20}$", name):
            return name
    except Exception as e:
        logger.warning("캐릭터명 추출 LLM 실패: %s", e)
    return None


def character_sync_node(state: AgentState) -> dict[str, Any]:
    """캐릭터 동기화 의도: 캐릭터명 추출 → 확인 문구 + pending_character_sync 반환."""
    query = (state.get("query") or "").strip()
    user_id = state.get("user_id")

    if not user_id:
        return {
            "final_answer": NEED_LOGIN,
            "references": [],
        }

    name = _extract_character_name(query)
    if not name:
        return {
            "final_answer": NO_NAME_MESSAGE,
            "references": [],
        }

    answer = (
        f"**{name}** 캐릭터 정보를 넥슨 API로 불러오려고 합니다. "
        f"{CONFIRM_INSTRUCTION}"
    )
    return {
        "final_answer": answer,
        "references": [],
        "pending_character_sync": name,
    }
