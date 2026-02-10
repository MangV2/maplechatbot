# -*- coding: utf-8 -*-
"""Qdrant payload 키 구조 확인용."""
import json
import sys
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

host = sys.argv[1] if len(sys.argv) > 1 else "qdrant"

client = QdrantClient(host=host, port=6333)
results = client.scroll(
    collection_name="maple_posts",
    scroll_filter=Filter(
        must=[FieldCondition(key="\uc9c1\uc5c5", match=MatchValue(value="\ud301\uacfc\ub178\ud558\uc6b0"))]
    ),
    limit=3,
    with_payload=True,
    with_vectors=False,
)
points = results[0]
print(f"Total: {len(points)}")
for i, pt in enumerate(points, 1):
    print(f"\n=== Point {i} (ID: {pt.id}) ===")
    print(f"Payload keys: {list(pt.payload.keys())}")
    for k, v in pt.payload.items():
        val_str = str(v)
        if len(val_str) > 200:
            val_str = val_str[:200] + "..."
        print(f"  {k}: {val_str}")
