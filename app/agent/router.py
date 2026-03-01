"""라우터 에이전트: LLM이 질문을 판단해 1~5 신뢰도로 분류, 3 미만이면 재질문."""
import logging
import re
from typing import Any

from app.agent.state import AgentState
from app.rag.openai_client import OpenAIClient

logger = logging.getLogger(__name__)

ROUTE_RAG = "rag"
ROUTE_GROWTH = "growth"
ROUTE_BOSS = "boss"
ROUTE_NEWBIE = "newbie"
ROUTE_CHARACTER_SYNC = "character_sync"
ROUTE_CLARIFY = "clarify"
ROUTE_NO_ANSWER = "no_answer"

ROUTE_NAMES = [ROUTE_RAG, ROUTE_GROWTH, ROUTE_BOSS, ROUTE_NEWBIE, ROUTE_CHARACTER_SYNC]

MIN_CONFIDENCE = 3  # 이 미만이면 재질문

ROUTER_SYSTEM = """당신은 메이플스토리 챗봇의 질문 분류기입니다.
사용자 질문이 아래 4가지 중 어디에 해당하는지, 각각 1~5점으로 평가하세요.
(5 = 확실히 해당 의도, 1 = 전혀 해당 없음)

- rag: 일반 질문 (직업 추천, 스킬, 육성, 장비 세팅, 인벤 게시글 기반 정보 등)
- growth: 성장 방향·우선순위 (다음에 뭘 올릴지, 스펙업 순서, 내실 채우기 순서, 체크리스트)
- boss: 보스 추천 (어떤 보스 도전 가능한지, 전투력·스펙 기준 보스 추천)
- newbie: 뉴비·초보 가이드 (처음 키우는 사람, 내실 체우기 가이드, 시작 가이드)
- character_sync: 캐릭터 정보 불러오기/동기화 ("OOO 정보 불러와줘", "서브캐 동기화", "캐릭터 정보 조회" 등)

**위 5가지 중 어디에도 해당하지 않으면** (메이플과 무관한 질문, 답변 불가 주제, 막말 등) BEST: none 으로 답하세요.

반드시 아래 형식으로만 답변하세요 (한 줄씩, 숫자는 1~5만).
RAG: [1-5]
GROWTH: [1-5]
BOSS: [1-5]
NEWBIE: [1-5]
CHARACTER_SYNC: [1-5]
BEST: [rag|growth|boss|newbie|character_sync|none]"""

CLARIFY_MESSAGE = """어떤 작업을 도와드릴지 알려주실 수 있을까요? 아래 중에서 골라 주시면 됩니다.

• **일반 질문** (직업/스킬/장비 등): 예) "히어로 스킬 추천", "아크 코어 세팅"
• **성장 방향**: 예) "다음에 뭘 올리지?", "스펙업 우선순위 알려줘"
• **보스 추천**: 예) "지금 스펙으로 어떤 보스 도전 가능?"
• **뉴비 가이드**: 예) "뉴비 내실 체우기", "초보 가이드"
• **캐릭터 정보 불러오기**: 예) "루나스톤 정보 불러와줘", "서브캐 동기화"

원하시는 내용을 조금 더 구체적으로 적어 주시면 바로 도와드릴게요."""

NO_ANSWER_MESSAGE = "질문하신 내용에 답할 정확한 정보가 없습니다."

# 보스 추천 의도: "보스" + 아래 중 하나면 LLM 없이 boss 노드로 직행
_BOSS_INTENT_KEYWORDS = ("도전", "가능", "잡을 수", "어디까지", "추천", "스펙", "내 캐릭터", "내 스펙")


def _is_boss_intent(query: str) -> bool:
    """보스 도전 가능/추천 질문이면 True. 키워드 기반 선라우팅용."""
    q = (query or "").strip()
    if "보스" not in q:
        return False
    return any(kw in q for kw in _BOSS_INTENT_KEYWORDS)


def _parse_router_response(text: str) -> tuple[dict[str, int], str | None]:
    """LLM 응답에서 RAG/GROWTH/BOSS/NEWBIE 점수와 BEST 추출. 실패 시 ({}, None)."""
    scores: dict[str, int] = {}
    best: str | None = None
    text = (text or "").strip().upper()

    for name in ["RAG", "GROWTH", "BOSS", "NEWBIE", "CHARACTER_SYNC"]:
        m = re.search(rf"{name}\s*:\s*(\d)", text, re.IGNORECASE)
        if m:
            v = int(m.group(1))
            key = "character_sync" if name == "CHARACTER_SYNC" else name.lower()
            scores[key] = max(1, min(5, v))

    m = re.search(r"BEST\s*:\s*(\w+)", text, re.IGNORECASE)
    if m:
        b = m.group(1).lower()
        if b == "none":
            best = ROUTE_NO_ANSWER
        elif b == "character_sync":
            best = ROUTE_CHARACTER_SYNC
        elif b in ROUTE_NAMES:
            best = b

    if not best and scores:
        best = max(scores, key=scores.get) if scores else None
    return scores, best


def router_agent_node(state: AgentState) -> dict[str, Any]:
    """LLM으로 질문 분류 후 route(및 필요 시 final_answer) 반환. 3 미만이면 clarify."""
    query = (state.get("query") or "").strip()
    if not query:
        return {
            "route": ROUTE_CLARIFY,
            "route_confidence": 0,
            "final_answer": "질문을 입력해 주세요.",
            "references": [],
        }

    # 보스 도전 가능/추천 질문은 키워드로 먼저 분류 (LLM이 RAG로 보내는 것 방지)
    if _is_boss_intent(query):
        logger.info("라우터: 키워드 선라우팅 → boss (질문=%r)", query)
        return {"route": ROUTE_BOSS, "route_confidence": 5}

    try:
        ai = OpenAIClient()
        resp = ai.chat_completion(
            messages=[
                {"role": "system", "content": ROUTER_SYSTEM},
                {"role": "user", "content": f"사용자 질문: {query}"},
            ],
            max_tokens=150,
            temperature=0.1,
        )
    except Exception as e:
        logger.exception("라우터 LLM 호출 실패: %s", e)
        return {"route": ROUTE_RAG, "route_confidence": 3}

    scores, best = _parse_router_response(resp)
    logger.info(
        "라우터 분류: 질문=%r | 점수=%s | BEST=%s",
        query, scores, best,
    )
    if not scores or not best:
        logger.info("라우터 결과: 파싱 실패 → clarify")
        return {
            "route": ROUTE_CLARIFY,
            "route_confidence": 0,
            "final_answer": CLARIFY_MESSAGE,
            "references": [],
        }

    if best == ROUTE_NO_ANSWER:
        logger.info("라우터 결과: none → no_answer")
        return {
            "route": ROUTE_NO_ANSWER,
            "route_confidence": 0,
            "final_answer": NO_ANSWER_MESSAGE,
            "references": [],
        }

    confidence = scores.get(best, 0)
    if confidence < MIN_CONFIDENCE:
        logger.info("라우터 결과: 신뢰도 부족(%s) → clarify", confidence)
        return {
            "route": ROUTE_CLARIFY,
            "route_confidence": confidence,
            "final_answer": CLARIFY_MESSAGE,
            "references": [],
        }

    logger.info("라우터 결과: route=%s, confidence=%s", best, confidence)
    return {"route": best, "route_confidence": confidence}


def route_query(state: AgentState) -> str:
    """conditional_edges용: state의 route 값으로 다음 노드 결정."""
    return (state.get("route") or ROUTE_RAG).strip().lower()
