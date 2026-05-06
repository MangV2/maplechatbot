"""보스 노드용 OpenAI Function Calling 도구 정의 및 실행기."""
import json
import logging
from typing import Any, Callable

from app.agent.data.boss_specs import get_doable_bosses

logger = logging.getLogger(__name__)

# ── 도구 스키마 (OpenAI tools 형식) ──────────────────────

BOSS_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "lookup_boss_table",
            "description": (
                "캐릭터 전투력 기준으로 도전 여유 있는 보스, 지금 도전해볼 만한 보스, "
                "다음 목표 보스를 조회합니다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "combat_power": {
                        "type": "integer",
                        "description": "캐릭터의 전투력 (정수, 예: 5000000)",
                    }
                },
                "required": ["combat_power"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_boss_tips",
            "description": (
                "메이플스토리 커뮤니티 게시판에서 보스 공략, 팁, 전략, 파티 구성 등의 정보를 검색합니다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "검색 키워드 (예: '카오스 루시드 공략', '듄켈 파티 팁')",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "반환할 결과 수 (기본값: 3, 최대: 5)",
                        "default": 3,
                    },
                },
                "required": ["query"],
            },
        },
    },
]


def make_boss_tool_executor(
    combat_power: int | None,
    rag_search_fn: Callable,
) -> Callable[[str, dict], Any]:
    """Boss Node 도구 실행기 팩토리.

    Args:
        combat_power: 캐릭터 전투력 (None 허용)
        rag_search_fn: (query: str, top_k: int) → list[dict] RAG 검색 함수
    """
    def executor(tool_name: str, args: dict) -> Any:
        if tool_name == "lookup_boss_table":
            cp = args.get("combat_power") or combat_power
            if cp is None:
                return {"error": "전투력 정보가 없습니다. 캐릭터 동기화 후 다시 시도해 주세요."}
            doable, try_soon, next_goal = get_doable_bosses(int(cp))
            return {
                "combat_power": cp,
                "doable_bosses": doable[-8:],   # 여유 있게 도전 가능한 최근 8개
                "challenge_now": try_soon[:5],  # 지금 도전해볼 만한 5개
                "next_goal": next_goal[:5],     # 다음 목표 5개
            }

        if tool_name == "search_boss_tips":
            query = args.get("query", "")
            top_k = min(int(args.get("top_k", 3)), 5)
            try:
                results = rag_search_fn(query, top_k)
                return [
                    {
                        "제목": r.get("제목", ""),
                        "직업": r.get("직업", ""),
                        "본문_요약": r.get("본문", "")[:400],
                        "작성일": r.get("작성일", ""),
                        "score": round(r.get("score", 0.0), 4),
                    }
                    for r in results
                ]
            except Exception as e:
                logger.warning("보스 팁 검색 실패: %s", e)
                return {"error": str(e)}

        logger.warning("알 수 없는 도구 호출: %s", tool_name)
        return {"error": f"Unknown tool: {tool_name}"}

    return executor
