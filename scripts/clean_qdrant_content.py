# -*- coding: utf-8 -*-
"""Qdrant에 저장된 본문 데이터에서 노이즈를 제거하는 마이그레이션 스크립트.

재크롤링 없이 기존 payload의 '본문' 필드만 정리합니다.
사용: docker compose exec api python scripts/clean_qdrant_content.py
"""
import re
import sys

from qdrant_client import QdrantClient
from qdrant_client.http.models import SetPayloadOperation, PointIdsList

HOST = sys.argv[1] if len(sys.argv) > 1 else "qdrant"
COLLECTION = "maple_posts"

# ── 노이즈 패턴 (크롤러와 동일) ─────────────────────────
NOISE_PATTERNS = [
    re.compile(r"\ubaa9\ub85d\s*\|?\s*\ub313\uae00\s*\(.*", re.DOTALL),
    re.compile(r"\d+\s*\uacf5\uc720\s*\uc2a4\ud06c\ub7a9\s*\uc2e0\uace0\ud558\uae30.*", re.DOTALL),
    re.compile(r"\ucd94\ucc9c\s*\ud655\uc778.*", re.DOTALL),
    re.compile(r"(EXP|\uacbd\ud5d8\uce58)\s*[\d,]+\s*\(.*", re.DOTALL),
    re.compile(r"(\uc778\ubca4\ucabd\uc9c0|\uc774\ub2c8\ud790\ub9c1|\ub354\ubcf4\uae30)\s*\ud3bc\uce58\uae30.*", re.DOTALL),
]


def clean_content(raw: str) -> str:
    """본문에서 노이즈 제거."""
    text = raw
    for pattern in NOISE_PATTERNS:
        text = pattern.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def main():
    client = QdrantClient(host=HOST, port=6333)
    info = client.get_collection(COLLECTION)
    total = info.points_count
    print(f"Collection: {COLLECTION}, Total points: {total}")

    offset = None
    cleaned = 0
    unchanged = 0
    batch_ids = []
    batch_payloads = []
    BATCH_SIZE = 100

    while True:
        results, offset = client.scroll(
            collection_name=COLLECTION,
            limit=100,
            offset=offset,
            with_payload=["\ubcf8\ubb38"],
            with_vectors=False,
        )

        for pt in results:
            raw = pt.payload.get("\ubcf8\ubb38", "")
            if not raw:
                unchanged += 1
                continue

            cleaned_text = clean_content(raw)

            if cleaned_text != raw:
                batch_ids.append(pt.id)
                batch_payloads.append({"\ubcf8\ubb38": cleaned_text})
                cleaned += 1
            else:
                unchanged += 1

            # 배치 업데이트
            if len(batch_ids) >= BATCH_SIZE:
                _flush(client, batch_ids, batch_payloads)
                print(f"  Progress: cleaned={cleaned}, unchanged={unchanged}")
                batch_ids.clear()
                batch_payloads.clear()

        if offset is None:
            break

    # 잔여 배치 처리
    if batch_ids:
        _flush(client, batch_ids, batch_payloads)

    print(f"\nDone! Cleaned: {cleaned}, Unchanged: {unchanged}, Total: {cleaned + unchanged}")


def _flush(client: QdrantClient, ids: list, payloads: list):
    """배치로 payload 업데이트."""
    for pid, payload in zip(ids, payloads):
        client.set_payload(
            collection_name=COLLECTION,
            payload=payload,
            points=[pid],
        )


if __name__ == "__main__":
    main()
