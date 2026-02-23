"""채팅 API 엔드포인트."""
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.auth.dependencies import get_current_user_optional
from app.models.user import User
from app.rag.loader import get_rag
from app.schemas.chat import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])


def _main_character(request: ChatRequest, user: User | None) -> str | None:
    """본캐 닉네임 (요청 > 로그인 사용자)."""
    if request.main_character_name:
        return request.main_character_name.strip()
    if user and user.main_character_name:
        return user.main_character_name
    return None


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user: Annotated[User | None, Depends(get_current_user_optional)],
):
    """질문에 대한 RAG 기반 답변을 반환합니다."""
    main_char = _main_character(request, user)
    try:
        rag = get_rag()
        result = rag.generate_answer(
            query=request.query.strip(),
            top_k=request.top_k,
            use_cot=request.use_cot,
            main_character_name=main_char,
        )
        return ChatResponse(**result)
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
):
    """스트리밍 방식으로 RAG 답변을 반환합니다 (SSE)."""
    main_char = _main_character(request, user)

    def event_generator():
        try:
            rag = get_rag()
            for event in rag.generate_answer_stream(
                query=request.query.strip(),
                top_k=request.top_k,
                use_cot=request.use_cot,
                main_character_name=main_char,
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
