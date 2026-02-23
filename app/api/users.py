"""회원 API (본캐 등록/조회)."""
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from sqlalchemy.orm import Session

router = APIRouter(prefix="/users", tags=["Users"])


class UserOut(BaseModel):
    """회원 정보 응답."""

    id: str
    email: str
    main_character_name: str | None = None


class UpdateMainCharacterRequest(BaseModel):
    """본캐 닉네임 수정 요청."""

    main_character_name: str = Field(..., min_length=1, max_length=100)


@router.get("/me", response_model=UserOut)
def get_me(
    user: Annotated[User, Depends(get_current_user)],
):
    """현재 로그인 사용자 정보 조회."""
    return UserOut(
        id=str(user.id),
        email=user.email,
        main_character_name=user.main_character_name,
    )


@router.patch("/me/main-character")
def update_main_character(
    req: UpdateMainCharacterRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """본캐 닉네임 등록/수정."""
    user.main_character_name = req.main_character_name.strip()
    db.commit()
    db.refresh(user)
    return {
        "status": "ok",
        "main_character_name": user.main_character_name,
    }
