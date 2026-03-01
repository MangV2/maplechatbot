"""RAG 스킬 노드: 기존 MapleRAG로 답변 생성 후 state 반영."""
import logging
from typing import Any

from app.agent.state import AgentState
from app.rag.loader import get_rag

logger = logging.getLogger(__name__)


def rag_node(state: AgentState) -> dict[str, Any]:
    """MapleRAG로 검색·답변 생성 후 final_answer, references 반환."""
    query = (state.get("query") or "").strip()
    if not query:
        return {"final_answer": "질문이 비어 있습니다.", "references": []}

    main_char = state.get("main_character_name")
    top_k = 5
    use_cot = True

    rag = get_rag()
    result = rag.generate_answer(
        query=query,
        top_k=top_k,
        use_cot=use_cot,
        main_character_name=main_char,
    )
    return {
        "final_answer": result.get("answer", ""),
        "references": result.get("references", []),
    }
