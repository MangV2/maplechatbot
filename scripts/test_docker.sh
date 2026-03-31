#!/usr/bin/env bash
# Docker 기반 테스트 실행 스크립트
# 사용:
#   ./scripts/test_docker.sh smoke
#   ./scripts/test_docker.sh unit
#   ./scripts/test_docker.sh all

set -euo pipefail
cd "$(dirname "$0")/.."

MODE="${1:-smoke}"
if [[ "$MODE" != "smoke" && "$MODE" != "unit" && "$MODE" != "all" ]]; then
  echo "Usage: ./scripts/test_docker.sh [smoke|unit|all]"
  exit 1
fi

if [[ ! -f .env ]]; then
  echo "ERROR: .env file not found. Copy .env.example to .env."
  exit 1
fi

echo "==> Building images"
docker compose -f docker-compose.yml -f docker-compose.test.yml build api test

echo "==> Starting dependencies"
docker compose -f docker-compose.yml -f docker-compose.test.yml up -d qdrant postgres api

echo "==> Waiting for API health"
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    break
  fi
  if [[ "$i" -eq 30 ]]; then
    echo "ERROR: API health check timed out. Check: docker compose logs api"
    exit 1
  fi
  sleep 2
done

case "$MODE" in
  smoke)
    PYTEST_ARGS="tests/unit/test_rag_router.py tests/unit/test_agent_router.py -v"
    ;;
  unit)
    PYTEST_ARGS="tests/unit -v"
    ;;
  all)
    PYTEST_ARGS="tests -v --cov=app"
    ;;
esac

echo "==> Running tests (mode=$MODE)"
docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test sh -lc "pytest ${PYTEST_ARGS}"

echo "Done: Docker tests (mode=$MODE)"
