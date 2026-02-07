#!/usr/bin/env bash
# 초기 데이터 적재: API가 기동된 뒤 소량 크롤링 트리거
# (maple_data.pkl 마이그레이션은 별도: docker compose exec api python -m scripts.migrate_faiss_to_qdrant)

set -e
API_URL="${API_BASE_URL:-http://localhost:8000}"

echo "Triggering initial crawl (small batch) at $API_URL ..."
curl -s -X POST "$API_URL/admin/crawl" \
  -H "Content-Type: application/json" \
  -d '{"max_jobs_per_group": 2, "max_pages": 1, "max_posts_per_page": 5}' \
  | head -20

echo ""
echo "Crawl triggered. Check status: curl $API_URL/admin/crawl/status"
echo "To run full migration from maple_data.pkl, mount the file and run:"
echo "  docker compose exec api python -m scripts.migrate_faiss_to_qdrant --data-path /data/maple_data.pkl"
