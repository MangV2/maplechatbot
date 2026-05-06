"""오케스트레이터 노드: 보스 공략 질문에 대해 병렬 서브에이전트 실행 후 LLM 통합 답변 생성.

서브에이전트:
  1. Boss Analyst  — 전투력 기반 정적 보스 테이블 조회 (I/O 없음, 즉시 반환)
  2. RAG Searcher  — 커뮤니티 보스 공략·팁 검색 (Qdrant + OpenAI Embedding)

두 에이전트를 ThreadPoolExecutor로 병렬 실행 후 LLM이 결과를 종합합니다.
"""
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any

from app.agent.data.boss_specs import get_doable_bosses
from app.agent.snapshot_utils import get_combat_power_from_snapshot, get_level_from_snapshot
from app.agent.state import AgentState
from app.rag.loader import get_rag
from app.rag.maple_rag import MapleRAG
from app.rag.openai_client import OpenAIClient

logger = logging.getLogger(__name__)

_SUBAGENT_TIMEOUT = 20  # seconds

ORCHESTRATOR_SYSTEM = """당신은 메이플스토리 보스 공략 전문 종합 어드바이저입니다.
아래 두 가지 정보를 바탕으로 사용자 질문에 상세히 답변하세요.

1. [캐릭터 스펙 & 보스 테이블]: 캐릭터 전투력 기준 도전 가능 보스 목록
2. [커뮤니티 공략 정보]: 실제 유저들의 보스 공략·팁·전략

답변 규칙:
- 전투력 기반 보스 추천과 커뮤니티 팁을 자연스럽게 통합하세요.
- 확실하지 않은 정보는 "~라는 의견이 있습니다"로 표현하세요.
- 한국어로 친절하고 구체적으로 답변하세요.
- 출처 정보는 자동 표시되므로 답변에 포함하지 마세요."""


def _boss_analyst(combat_power: int | None) -> dict[str, Any]:
    """서브에이전트 1: 전투력 기반 보스 테이블 조회."""
    if combat_power is None:
        return {"combat_power": None, "doable": [], "try_soon": [], "next_goal": []}
    doable, try_soon, next_goal = get_doable_bosses(combat_power)
    return {
        "combat_power": combat_power,
        "doable": doable[-8:],
        "try_soon": try_soon[:5],
        "next_goal": next_goal[:5],
    }


def _rag_searcher(query: str, top_k: int = 3) -> list[dict[str, Any]]:
    """서브에이전트 2: RAG로 커뮤니티 보스 공략·팁 검색."""
    rag = get_rag()
    return rag.search(query, top_k=top_k)


def _format_boss_summary(boss_data: dict[str, Any]) -> str:
    """보스 테이블 조회 결과를 텍스트로 포맷."""
    cp = boss_data.get("combat_power")
    if cp is None:
        return "전투력 정보 없음 (캐릭터 동기화 필요)"

    lines = [f"전투력: {cp:,}"]
    if boss_data.get("doable"):
        lines.append("도전 여유 있는 보스: " + ", ".join(boss_data["doable"]))
    if boss_data.get("try_soon"):
        lines.append("지금 도전해볼 만한 보스: " + ", ".join(boss_data["try_soon"]))
    if boss_data.get("next_goal"):
        lines.append("다음 목표 보스: " + ", ".join(boss_data["next_goal"]))
    return "\n".join(lines)


def orchestrator_node(state: AgentState) -> dict[str, Any]:
    """보스 공략 질문에 대해 병렬 서브에이전트 실행 후 LLM 통합 답변."""
    query = state.get("query", "")
    snapshot = state.get("character_snapshot")
    combat_power = get_combat_power_from_snapshot(snapshot)
    level = get_level_from_snapshot(snapshot)
    main_char = state.get("main_character_name")

    # ── 서브에이전트 병렬 실행 ────────────────────────────
    boss_data: dict[str, Any] = {}
    rag_results: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_boss = executor.submit(_boss_analyst, combat_power)
        future_rag = executor.submit(_rag_searcher, query, 3)

        try:
            boss_data = future_boss.result(timeout=_SUBAGENT_TIMEOUT)
        except FuturesTimeoutError:
            logger.warning("보스 테이블 조회 타임아웃")
        except Exception as e:
            logger.warning("보스 테이블 조회 실패: %s", e)

        try:
            rag_results = future_rag.result(timeout=_SUBAGENT_TIMEOUT)
        except FuturesTimeoutError:
            logger.warning("RAG 검색 타임아웃")
        except Exception as e:
            logger.warning("RAG 검색 실패: %s", e)

    # ── 컨텍스트 구성 ─────────────────────────────────────
    boss_summary = _format_boss_summary(boss_data)

    rag_context = ""
    if rag_results:
        rag = get_rag()
        rag_context = rag._build_context(rag_results)

    char_header = []
    if main_char:
        char_header.append(f"캐릭터: {main_char}")
    if level:
        char_header.append(f"레벨: {level}")
    char_str = ", ".join(char_header) if char_header else "캐릭터 정보 없음"

    user_content = (
        f"[캐릭터 정보]\n{char_str}\n\n"
        f"[캐릭터 스펙 & 보스 테이블]\n{boss_summary}\n\n"
        f"[커뮤니티 공략 정보]\n{rag_context or '검색된 커뮤니티 정보 없음'}\n\n"
        f"질문: {query}"
    )

    # ── LLM 종합 답변 ─────────────────────────────────────
    try:
        ai = OpenAIClient()
        answer = ai.chat_completion(
            messages=[
                {"role": "system", "content": ORCHESTRATOR_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
        )
    except Exception as e:
        logger.exception("오케스트레이터 LLM 호출 실패: %s", e)
        answer = boss_summary or "답변 생성 중 오류가 발생했습니다."

    references = MapleRAG._build_references(rag_results) if rag_results else []
    return {"final_answer": answer, "references": references}
