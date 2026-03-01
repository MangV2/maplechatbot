"""채팅 API 요청/응답 스키마."""
from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """POST /chat 요청."""

    query: str = Field(..., min_length=1, max_length=2000, description="질문")
    top_k: int = Field(default=5, ge=1, le=10, description="검색할 참고 문서 수")
    use_cot: bool = Field(default=True, description="CoT 질문 분석 사용 여부")
    main_character_name: str | None = Field(
        default=None, max_length=100, description="본캐 닉네임 (에이전트용)"
    )


class ReferenceItem(BaseModel):
    """참고 문서 항목."""

    직업: str = ""
    직업군: str = ""
    제목: str = ""
    작성일: str = ""
    similarity_score: float = 0.0
    본문_요약: str = ""


class ChatResponse(BaseModel):
    """POST /chat 응답."""

    answer: str = Field(..., description="RAG 기반 답변")
    references: list[ReferenceItem] = Field(
        default_factory=list, description="참고 문서 목록"
    )
    pending_character_sync: str | None = Field(
        default=None,
        description="캐릭터 동기화 확인 대기 중인 캐릭터명. 프론트에서 '동기화 진행' 시 이 이름으로 API 호출.",
    )


class HealthResponse(BaseModel):
    """GET /health 응답."""

    status: str = "ok"
    qdrant_status: str = "unknown"
    document_count: int = 0
