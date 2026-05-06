"""chat_sessions 테이블에 user_id 컬럼 추가 마이그레이션.

Usage:
    python -m scripts.migrate_add_user_id_to_sessions

이미 user_id 컬럼이 있으면 스킵합니다.
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def migrate():
    """chat_sessions에 user_id 컬럼 추가."""
    from sqlalchemy import text

    from app.database import engine

    with engine.connect() as conn:
        # user_id 컬럼 존재 여부 확인
        r = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'chat_sessions' AND column_name = 'user_id'
        """))
        if r.fetchone():
            logger.info("user_id 컬럼이 이미 존재합니다. 마이그레이션 스킵.")
            return

        logger.info("chat_sessions에 user_id 컬럼 추가 중...")
        conn.execute(text("""
            ALTER TABLE chat_sessions
            ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE SET NULL
        """))
        conn.execute(text("""
            CREATE INDEX ix_chat_sessions_user_id ON chat_sessions(user_id)
        """))
        conn.commit()
        logger.info("마이그레이션 완료.")


if __name__ == "__main__":
    try:
        migrate()
    except Exception as e:
        logger.exception("마이그레이션 실패: %s", e)
        sys.exit(1)
