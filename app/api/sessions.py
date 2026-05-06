"""채팅 세션 API 엔드포인트."""
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user_optional
from app.database import get_db
from app.models.chat_history import ChatMessage, ChatSession
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["Sessions"])


# ── 스키마 ─────────────────────────────────────────────


class SessionOut(BaseModel):
    """세션 요약 응답."""

    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0

    model_config = {"from_attributes": True}


class SessionDetail(BaseModel):
    """세션 상세 (메시지 포함) 응답."""

    id: str
    title: str
    messages: list[dict]


class MessageOut(BaseModel):
    """메시지 응답."""

    role: str
    content: str
    references: list | None = None


class CreateSessionResponse(BaseModel):
    """세션 생성 응답."""

    id: str
    title: str


class SaveMessageRequest(BaseModel):
    """메시지 저장 요청."""

    role: str = Field(..., pattern="^(user|assistant)$")
    content: str
    references: list | None = None


class UpdateTitleRequest(BaseModel):
    """세션 제목 변경 요청."""

    title: str = Field(..., min_length=1, max_length=200)


# ── 엔드포인트 ─────────────────────────────────────────


def _can_access_session(session: ChatSession, user: User | None) -> bool:
    """세션 접근 권한: user_id가 없으면 누구나, 있으면 본인만."""
    if session.user_id is None:
        return True
    return user is not None and str(session.user_id) == str(user.id)


@router.get("", response_model=list[SessionOut])
def list_sessions(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_current_user_optional)],
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """세션 목록 (최신순). 로그인 시 본인 세션만, 비로그인 시 익명(user_id IS NULL) 세션만."""
    q = db.query(ChatSession).order_by(ChatSession.updated_at.desc())
    if user is not None:
        q = q.filter(ChatSession.user_id == user.id)
    else:
        q = q.filter(ChatSession.user_id.is_(None))
    sessions = q.offset(offset).limit(limit).all()
    result = []
    for s in sessions:
        result.append(
            SessionOut(
                id=str(s.id),
                title=s.title,
                created_at=s.created_at.isoformat(),
                updated_at=s.updated_at.isoformat(),
                message_count=len(s.messages),
            )
        )
    return result


@router.post("", response_model=CreateSessionResponse)
def create_session(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_current_user_optional)],
):
    """새 채팅 세션 생성. 로그인 시 user_id 설정."""
    session = ChatSession(user_id=user.id if user else None)
    db.add(session)
    db.commit()
    db.refresh(session)
    return CreateSessionResponse(id=str(session.id), title=session.title)


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_current_user_optional)],
):
    """세션의 전체 대화 내역 조회."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="잘못된 세션 ID")

    session = db.query(ChatSession).filter(ChatSession.id == sid).first()
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    if not _can_access_session(session, user):
        raise HTTPException(status_code=403, detail="이 세션에 접근할 수 없습니다")

    messages = []
    for m in session.messages:
        messages.append({
            "role": m.role,
            "content": m.content,
            "references": m.references,
        })

    return SessionDetail(
        id=str(session.id),
        title=session.title,
        messages=messages,
    )


@router.post("/{session_id}/messages")
def save_message(
    session_id: str,
    req: SaveMessageRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_current_user_optional)],
):
    """세션에 메시지 저장."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="잘못된 세션 ID")

    session = db.query(ChatSession).filter(ChatSession.id == sid).first()
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    if not _can_access_session(session, user):
        raise HTTPException(status_code=403, detail="이 세션에 접근할 수 없습니다")

    msg = ChatMessage(
        session_id=sid,
        role=req.role,
        content=req.content,
        references=req.references,
    )
    db.add(msg)

    # 첫 사용자 메시지로 세션 제목 자동 설정
    if session.title == "새 대화" and req.role == "user":
        session.title = req.content[:50] + ("..." if len(req.content) > 50 else "")

    db.commit()
    return {"status": "ok"}


@router.patch("/{session_id}/title")
def update_title(
    session_id: str,
    req: UpdateTitleRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_current_user_optional)],
):
    """세션 제목 변경."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="잘못된 세션 ID")

    session = db.query(ChatSession).filter(ChatSession.id == sid).first()
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    if not _can_access_session(session, user):
        raise HTTPException(status_code=403, detail="이 세션에 접근할 수 없습니다")

    session.title = req.title
    db.commit()
    return {"status": "ok"}


@router.delete("/{session_id}")
def delete_session(
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_current_user_optional)],
):
    """세션 삭제."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="잘못된 세션 ID")

    session = db.query(ChatSession).filter(ChatSession.id == sid).first()
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    if not _can_access_session(session, user):
        raise HTTPException(status_code=403, detail="이 세션에 접근할 수 없습니다")

    db.delete(session)
    db.commit()
    return {"status": "ok"}
