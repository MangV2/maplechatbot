#!/usr/bin/env bash
# 초기 데이터 적재: API가 기동된 뒤 소량 크롤링 트리거

set -e
API_URL="${API_BASE_URL:-http://localhost:8000}"

echo "Triggering initial crawl (small batch) at $API_URL ..."
curl -s -X POST "$API_URL/admin/crawl" \
  -H "Content-Type: application/json" \
  -d '{}' \
  | head -20

echo ""
echo "Crawl triggered. Check status: curl $API_URL/admin/crawl/status"
