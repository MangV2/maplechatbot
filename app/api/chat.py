"""채팅 API 엔드포인트."""
import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.rag.loader import get_rag
from app.schemas.chat import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """질문에 대한 RAG 기반 답변을 반환합니다."""
    try:
        rag = get_rag()
        result = rag.generate_answer(
            query=request.query.strip(),
            top_k=request.top_k,
            use_cot=request.use_cot,
        )
        return ChatResponse(**result)
    except Exception as e:
        logger.exception("채팅 처리 실패: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"답변 생성 중 오류가 발생했습니다: {str(e)}",
        )


@router.post("/stream")
async def chat_stream(request: ChatRequest):
    """스트리밍 방식으로 RAG 답변을 반환합니다 (SSE)."""

    def event_generator():
        try:
            rag = get_rag()
            for event in rag.generate_answer_stream(
                query=request.query.strip(),
                top_k=request.top_k,
                use_cot=request.use_cot,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.exception("스트리밍 처리 실패: %s", e)
            error_event = {"type": "error", "content": str(e)}
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
