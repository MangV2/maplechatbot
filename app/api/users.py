"""회원 API (본캐 등록/조회, 캐릭터 동기화)."""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.character_snapshot import CharacterSnapshot
from app.models.user import User
from app.nexon.client import NexonMapleClient, NexonMapleClientError

logger = logging.getLogger(__name__)

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


@router.post("/me/character-sync")
def character_sync(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    character_name: str | None = Query(None, min_length=1, max_length=100),
):
    """넥슨 API로 캐릭터 정보 조회 후 DB에 저장. 본캐 또는 character_name 지정."""
    name = (character_name or user.main_character_name or "").strip()
    if not name:
        raise HTTPException(
            status_code=400,
            detail="본캐가 등록되어 있지 않습니다. 본캐를 먼저 등록하거나 character_name 쿼리를 넣어 주세요.",
        )
    try:
        client = NexonMapleClient()
        snapshot_data = client.fetch_full_snapshot(name)
        client.close()
    except NexonMapleClientError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    ocid = snapshot_data.get("ocid", "")
    existing = (
        db.query(CharacterSnapshot)
        .filter(
            CharacterSnapshot.user_id == user.id,
            CharacterSnapshot.character_name == name,
        )
        .first()
    )
    if existing:
        existing.ocid = ocid
        existing.snapshot = snapshot_data
        db.commit()
        db.refresh(existing)
        snapshot = existing
    else:
        snapshot = CharacterSnapshot(
            user_id=user.id,
            character_name=name,
            ocid=ocid,
            snapshot=snapshot_data,
        )
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)

    return {
        "status": "ok",
        "character_name": snapshot.character_name,
        "fetched_at": snapshot.fetched_at.isoformat(),
        "notice": "API를 통해 수집한 데이터는 30일 이내에 갱신해야 할 의무가 있습니다.",
    }
