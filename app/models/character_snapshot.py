"""캐릭터 스냅샷 모델 (넥슨 API 조회 결과 저장)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class CharacterSnapshot(Base):
    """유저별 캐릭터 1인당 최신 스냅샷 1건. sync 시 upsert."""

    __tablename__ = "character_snapshots"
    __table_args__ = (
        UniqueConstraint("user_id", "character_name", name="uq_character_snapshot_user_char"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    character_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    ocid: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="character_snapshots",
    )
