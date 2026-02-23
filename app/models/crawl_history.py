"""크롤링 이력 모델."""
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CrawlHistory(Base):
    """크롤링 실행 이력 (영구 저장)."""

    __tablename__ = "crawl_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(20), nullable=False)  # "scheduled" | "manual"
    crawled: Mapped[int] = mapped_column(Integer, nullable=False)
    upserted: Mapped[int] = mapped_column(Integer, nullable=False)
    skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors: Mapped[int] = mapped_column(Integer, nullable=False)
    elapsed_seconds: Mapped[float] = mapped_column(Float, nullable=False)
