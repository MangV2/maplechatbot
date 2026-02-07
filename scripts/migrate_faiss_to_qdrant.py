"""FAISS 데이터(maple_data.pkl)를 Qdrant로 마이그레이션하는 스크립트.

Usage:
    python -m scripts.migrate_faiss_to_qdrant
    python -m scripts.migrate_faiss_to_qdrant --data-path maple_data.pkl --batch-size 50

환경 변수 (.env 또는 직접 설정):
    OPENAI_API_KEY: OpenAI API 키
    QDRANT_HOST / QDRANT_PORT / QDRANT_COLLECTION
"""
import argparse
import logging
import sys
import time
from pathlib import Path

import pandas as pd

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def migrate(data_path: str, batch_size: int = 50):
    """maple_data.pkl → OpenAI 임베딩 → Qdrant 적재."""
    from app.rag.openai_client import OpenAIClient
    from app.rag.qdrant_store import QdrantStore

    # ── 1. 데이터 로드 ──
    pkl_path = Path(data_path)
    if not pkl_path.exists():
        logger.error("데이터 파일을 찾을 수 없습니다: %s", pkl_path)
        sys.exit(1)

    df = pd.read_pickle(str(pkl_path))
    logger.info("데이터 로드 완료: %d 건", len(df))
    logger.info("컬럼: %s", list(df.columns))

    # ── 2. 클라이언트 초기화 ──
    store = QdrantStore()
    ai = OpenAIClient()
    logger.info(
        "Qdrant(%s:%s/%s) / OpenAI 클라이언트 초기화 완료",
        store.client._client.rest_uri if hasattr(store.client, '_client') else "?",
        "",
        store.collection_name,
    )

    # ── 3. 배치 임베딩 & 적재 ──
    total = len(df)
    success = 0
    errors = 0
    start_time = time.time()

    for i in range(0, total, batch_size):
        batch_df = df.iloc[i : i + batch_size]
        batch_end = min(i + batch_size, total)

        # 임베딩용 텍스트 생성
        texts = []
        for _, row in batch_df.iterrows():
            text = (
                f"직업: {row.get('직업', '')} | "
                f"제목: {row.get('제목', '')} | "
                f"{str(row.get('본문', ''))[:500]}"
            )
            texts.append(text)

        try:
            # 임베딩 생성
            vectors = ai.create_embeddings_batch(texts)

            # 페이로드 구성
            ids = list(range(i, batch_end))
            payloads = []
            for _, row in batch_df.iterrows():
                payloads.append({
                    "직업": str(row.get("직업", "")),
                    "직업군": str(row.get("직업군", "")),
                    "제목": str(row.get("제목", "")),
                    "작성일": str(row.get("작성일", "")),
                    "본문": str(row.get("본문", "")),
                    "댓글": str(row.get("댓글", "")),
                })

            # Qdrant 적재
            store.upsert_batch(ids, vectors, payloads, batch_size=batch_size)
            success += len(batch_df)

            elapsed = time.time() - start_time
            rate = success / elapsed if elapsed > 0 else 0
            logger.info(
                "진행: %d/%d (%.1f%%) | 성공: %d, 실패: %d | 속도: %.1f건/초",
                batch_end, total, batch_end / total * 100,
                success, errors, rate,
            )

            # OpenAI API rate limit 대비 대기
            time.sleep(0.5)

        except Exception as e:
            errors += len(batch_df)
            logger.error("배치 %d-%d 실패: %s", i, batch_end, e)
            time.sleep(2)  # 에러 시 더 긴 대기

    elapsed_total = time.time() - start_time
    logger.info("=" * 60)
    logger.info("마이그레이션 완료")
    logger.info("  성공: %d / 실패: %d / 전체: %d", success, errors, total)
    logger.info("  소요 시간: %.1f초", elapsed_total)
    logger.info("  Qdrant 문서 수: %d", store.count())


def main():
    parser = argparse.ArgumentParser(description="FAISS → Qdrant 마이그레이션")
    parser.add_argument(
        "--data-path",
        default="maple_data.pkl",
        help="maple_data.pkl 파일 경로 (기본: 프로젝트 루트)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="배치 크기 (기본: 50, OpenAI API 제한 고려)",
    )
    args = parser.parse_args()
    migrate(args.data_path, args.batch_size)


if __name__ == "__main__":
    main()
