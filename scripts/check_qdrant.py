# -*- coding: utf-8 -*-
"""Qdrant 데이터 조회 스크립트."""
import sys
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

host = sys.argv[1] if len(sys.argv) > 1 else "qdrant"
job_value = sys.argv[2] if len(sys.argv) > 2 else "\ud301\uacfc\ub178\ud558\uc6b0"
limit = int(sys.argv[3]) if len(sys.argv) > 3 else 10

client = QdrantClient(host=host, port=6333)
results = client.scroll(
    collection_name="maple_posts",
    scroll_filter=Filter(
        must=[FieldCondition(key="\uc9c1\uc5c5", match=MatchValue(value=job_value))]
    ),
    limit=limit,
    with_payload=True,
    with_vectors=False,
)
points = results[0]
print(f"Total: {len(points)}")
print("=" * 80)
for i, pt in enumerate(points, 1):
    p = pt.payload
    print(f"[{i}] ID: {pt.id}")
    print(f"    Title : {p.get('title', 'N/A')}")
    print(f"    Group : {p.get('\uc9c1\uc5c5\uad70', 'N/A')} / Job: {p.get('\uc9c1\uc5c5', 'N/A')}")
    print(f"    URL   : {p.get('url', 'N/A')}")
    content = p.get("content", "")
    print(f"    Content: {content[:120]}...")
    print("-" * 80)
