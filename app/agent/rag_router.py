"""RAG 전용 라우터: 규칙 우선 + LLM 보조로 검색 필터 결정."""
import logging
from typing import Any

from app.rag.maple_rag import (
    ANALYSIS_SYSTEM_PROMPT,
    _resolve_group_from_query,
    _resolve_job_from_query,
)

logger = logging.getLogger(__name__)

_VALID_GROUPS = ("전사", "마법사", "궁수", "도적", "해적")


def _parse_rag_router_response(text: str, job_list: list[str]) -> dict[str, Any]:
    """LLM 응답 파싱. 실패 시 all 라우트."""
    route = "all"
    filter_job = None
    filter_group = None
    confidence = 2

    for raw in (text or "").splitlines():
        line = raw.strip()
        if line.startswith("ROUTE:"):
            v = line.split("ROUTE:", 1)[-1].strip().lower()
            if v in ("job", "group", "all"):
                route = v
        elif line.startswith("FILTER_JOB:"):
            v = line.split("FILTER_JOB:", 1)[-1].strip()
            if v and v.lower() != "none" and v in job_list:
                filter_job = v
        elif line.startswith("FILTER_GROUP:"):
            v = line.split("FILTER_GROUP:", 1)[-1].strip()
            if v and v.lower() != "none" and v in _VALID_GROUPS:
                filter_group = v
        elif line.startswith("CONFIDENCE:"):
            v = line.split("CONFIDENCE:", 1)[-1].strip()
            if v.isdigit():
                confidence = max(1, min(5, int(v)))

    if route == "job" and not filter_job:
        route = "all"
    if route == "group" and not filter_group:
        route = "all"

    return {
        "retrieval_route": route,
        "filter_job": filter_job,
        "filter_group": filter_group,
        "retrieval_confidence": confidence,
    }


def route_rag_query(query: str, rag: Any) -> dict[str, Any]:
    """질문을 검색 라우트(job/group/all)로 분류."""
    job_list = list(getattr(rag, "job_list", []) or [])
    local_job = _resolve_job_from_query(query, job_list) if job_list else None
    local_group = _resolve_group_from_query(query)

    if local_job:
        return {
            "retrieval_route": "job",
            "filter_job": local_job,
            "filter_group": None,
            "retrieval_source": "rule",
            "retrieval_confidence": 5,
            "retrieval_reasoning": f"별칭 매핑: {local_job}",
        }

    if local_group:
        return {
            "retrieval_route": "group",
            "filter_job": None,
            "filter_group": local_group,
            "retrieval_source": "rule",
            "retrieval_confidence": 5,
            "retrieval_reasoning": f"직업군 매핑: {local_group}",
        }

    if not job_list:
        return {
            "retrieval_route": "all",
            "filter_job": None,
            "filter_group": None,
            "retrieval_source": "fallback",
            "retrieval_confidence": 1,
            "retrieval_reasoning": "직업 목록 없음",
        }

    prompt = f"""사용자 질문을 보고 RAG 검색 전략을 결정하세요.

<DB 직업 목록>
{", ".join(job_list)}

<직업군 목록>
전사, 마법사, 궁수, 도적, 해적

<질문>
{query}

<판단 규칙>
1) 특정 직업 질문이면 ROUTE는 job, FILTER_JOB에 정확한 직업명
2) 특정 직업군 질문이면 ROUTE는 group, FILTER_GROUP에 직업군명
3) 비교/추천/일반 정보 질문이면 ROUTE는 all
4) 확신이 낮으면 all을 선택

<출력 형식 - 반드시 아래 4줄>
ROUTE: [job|group|all]
FILTER_JOB: [정확한 직업명 또는 none]
FILTER_GROUP: [전사|마법사|궁수|도적|해적|none]
CONFIDENCE: [1-5]"""

    try:
        response = rag.ai.chat_completion(
            messages=[
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=100,
            temperature=0.1,
        )
        parsed = _parse_rag_router_response(response, job_list)
        parsed["retrieval_source"] = "llm"
        parsed["retrieval_reasoning"] = response.strip()
        return parsed
    except Exception as e:
        logger.exception("RAG 라우터 LLM 호출 실패: %s", e)
        return {
            "retrieval_route": "all",
            "filter_job": None,
            "filter_group": None,
            "retrieval_source": "fallback",
            "retrieval_confidence": 1,
            "retrieval_reasoning": "LLM 호출 실패",
        }
