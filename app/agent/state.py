"""에이전트 그래프 공통 상태 (TypedDict)."""
from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """라우터 및 스킬 노드가 읽고 쓰는 공통 상태."""

    messages: list[dict[str, str]]
    query: str
    user_id: str | None
    main_character_name: str | None
    character_snapshot: dict[str, Any] | None
    route: str
    route_confidence: int  # 1~5, 3 미만이면 재질문
    tool_results: dict[str, Any]
    final_answer: str
    references: list[dict[str, Any]]
    pending_character_sync: str | None  # 채팅으로 동기화 요청 시 캐릭터명 (확인 후 프론트에서 API 호출)
    retrieval_route: str  # rag 내부 검색 라우트(job/group/all)
    retrieval_source: str  # rag 라우트 판단 근거(rule/llm/fallback)
    retrieval_confidence: int  # rag 라우트 신뢰도 1~5
    retrieval_reasoning: str  # rag 라우트 판단 원문/사유
    filter_job: str | None  # rag 검색 직업 필터
    filter_group: str | None  # rag 검색 직업군 필터
