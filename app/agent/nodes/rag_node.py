"""RAG 스킬 노드: 라우터에서 추출한 직업/직업군 필터를 재사용해 LLM 호출 최소화."""
import logging
from typing import Any

from app.agent.state import AgentState
from app.rag.loader import get_rag

logger = logging.getLogger(__name__)


def rag_node(state: AgentState) -> dict[str, Any]:
    """MapleRAG로 검색·답변 생성 후 final_answer, references 반환.

    라우터가 filter_job/filter_group을 state에 넣어뒀으면 analyze_query() LLM 호출을 건너뜀.
    """
    query = (state.get("query") or "").strip()
    if not query:
        return {"final_answer": "질문이 비어 있습니다.", "references": []}

    main_char = state.get("main_character_name")

    # 라우터에서 추출한 필터가 있으면 재사용 (LLM analyze_query 호출 생략)
    router_set_filters = "filter_job" in state or "filter_group" in state
    pre_filter_job = state.get("filter_job") if router_set_filters else None
    pre_filter_group = state.get("filter_group") if router_set_filters else None

    rag = get_rag()
    result = rag.generate_answer(
        query=query,
        top_k=5,
        use_cot=True,
        main_character_name=main_char,
        pre_filter_job=pre_filter_job,
        pre_filter_group=pre_filter_group,
        skip_analysis=router_set_filters,
    )
    return {
        "final_answer": result.get("answer", ""),
        "references": result.get("references", []),
    }
