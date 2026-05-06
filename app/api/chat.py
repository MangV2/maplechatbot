"""채팅 API 엔드포인트 (에이전트 그래프 진입). 모든 질문은 라우터를 거친 뒤, RAG는 스트리밍·나머지는 한 번에 SSE로 응답."""
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agent.graph import invoke as agent_invoke
from app.agent.router import router_agent_node
from app.agent.nodes.boss_node import boss_node
from app.agent.nodes.character_sync_node import character_sync_node
from app.agent.nodes.orchestrator_node import orchestrator_node
from app.agent.state import AgentState
from app.auth.dependencies import get_current_user_optional
from app.database import get_db
from app.models.character_snapshot import CharacterSnapshot
from app.models.user import User
from app.rag.loader import get_rag
from app.schemas.chat import ChatRequest, ChatResponse

# route → 해당 노드 함수 (스트리밍이 아닌 노드)
_ROUTE_NODE = {
    "boss": boss_node,
    "orchestrator": orchestrator_node,
    "character_sync": character_sync_node,
}

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])


def _main_character(request: ChatRequest, user: User | None) -> str | None:
    """본캐 닉네임 (요청 > 로그인 사용자)."""
    if request.main_character_name:
        return request.main_character_name.strip()
    if user and user.main_character_name:
        return user.main_character_name
    return None


def _get_character_snapshot(db: Session, user: User | None, main_char: str | None) -> dict | None:
    """로그인 유저·본캐 기준 최신 스냅샷 dict. 없으면 None."""
    if not user or not main_char:
        return None
    row = (
        db.query(CharacterSnapshot)
        .filter(
            CharacterSnapshot.user_id == user.id,
            CharacterSnapshot.character_name == main_char,
        )
        .order_by(CharacterSnapshot.fetched_at.desc())
        .first()
    )
    return row.snapshot if row and getattr(row, "snapshot", None) else None


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user: Annotated[User | None, Depends(get_current_user_optional)],
    db: Annotated[Session, Depends(get_db)],
):
    """질문에 대한 에이전트(RAG 등) 기반 답변을 반환합니다."""
    main_char = _main_character(request, user)
    character_snapshot = _get_character_snapshot(db, user, main_char)
    try:
        result = agent_invoke(
            query=request.query.strip(),
            main_character_name=main_char,
            user_id=str(user.id) if user else None,
            character_snapshot=character_snapshot,
        )
        return ChatResponse(
            answer=result["answer"],
            references=result["references"],
            pending_character_sync=result.get("pending_character_sync"),
        )
    except Exception as e:
        logger.exception("채팅 처리 실패: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"답변 생성 중 오류가 발생했습니다: {str(e)}",
        )


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    user: Annotated[User | None, Depends(get_current_user_optional)],
    db: Annotated[Session, Depends(get_db)],
):
    """모든 질문이 라우터를 거친 뒤, RAG는 스트리밍·나머지(boss/growth 등)는 한 번에 SSE로 응답."""
    main_char = _main_character(request, user)
    character_snapshot = _get_character_snapshot(db, user, main_char)
    query = request.query.strip()

    def event_generator():
        try:
            initial: AgentState = {
                "query": query,
                "main_character_name": main_char,
                "user_id": str(user.id) if user else None,
                "character_snapshot": character_snapshot,
            }
            router_out = router_agent_node(initial)
            state: AgentState = {**initial, **router_out}
            route = (state.get("route") or "rag").strip().lower()

            # clarify / no_answer: 라우터가 이미 final_answer 반환
            if route in ("clarify", "no_answer"):
                answer = state.get("final_answer") or ""
                refs = state.get("references") or []
                for ev in (
                    {"type": "answer_chunk", "content": answer},
                    {"type": "done", "content": ""},
                    {"type": "references", "content": refs},
                ):
                    yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return

            # rag: 기존 RAG 스트리밍 (라우터에서 추출한 필터 재사용)
            if route == "rag":
                router_set_filters = "filter_job" in state or "filter_group" in state
                rag = get_rag()
                for event in rag.generate_answer_stream(
                    query=query,
                    top_k=request.top_k,
                    use_cot=request.use_cot,
                    main_character_name=main_char,
                    pre_filter_job=state.get("filter_job") if router_set_filters else None,
                    pre_filter_group=state.get("filter_group") if router_set_filters else None,
                    skip_analysis=router_set_filters,
                ):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return

            # boss / growth / newbie / character_sync: 해당 노드 실행 후 한 번에 SSE
            node_fn = _ROUTE_NODE.get(route)
            if node_fn:
                out = node_fn(state)
                answer = out.get("final_answer") or ""
                refs = out.get("references") or []
                pending_sync = out.get("pending_character_sync")
                yield f"data: {json.dumps({'type': 'answer_chunk', 'content': answer}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'content': ''}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'references', 'content': refs}, ensure_ascii=False)}\n\n"
                if pending_sync:
                    yield f"data: {json.dumps({'type': 'pending_character_sync', 'content': pending_sync}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return

            # fallback: rag로 처리
            rag = get_rag()
            for event in rag.generate_answer_stream(
                query=query,
                top_k=request.top_k,
                use_cot=request.use_cot,
                main_character_name=main_char,
                pre_filter_job=state.get("filter_job"),
                pre_filter_group=state.get("filter_group"),
                skip_analysis="filter_job" in state or "filter_group" in state,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.exception("스트리밍 처리 실패: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
