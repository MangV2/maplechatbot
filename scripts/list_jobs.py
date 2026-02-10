# -*- coding: utf-8 -*-
"""Qdrant에 저장된 직업/직업군 목록 확인."""
import sys
from collections import Counter
from qdrant_client import QdrantClient

host = sys.argv[1] if len(sys.argv) > 1 else "qdrant"
client = QdrantClient(host=host, port=6333)

jobs: Counter = Counter()
groups: Counter = Counter()
offset = None

while True:
    results, offset = client.scroll(
        collection_name="maple_posts",
        limit=100,
        offset=offset,
        with_payload=["\uc9c1\uc5c5", "\uc9c1\uc5c5\uad70"],
    )
    for pt in results:
        job = pt.payload.get("\uc9c1\uc5c5", "")
        group = pt.payload.get("\uc9c1\uc5c5\uad70", "")
        if job:
            jobs[job] += 1
        if group:
            groups[group] += 1
    if offset is None:
        break

print("=== JOB GROUPS ===")
for g, cnt in groups.most_common():
    print(f"  {g}: {cnt}")

print(f"\n=== JOBS ({len(jobs)}) ===")
for j, cnt in jobs.most_common():
    print(f"  {j}: {cnt}")
