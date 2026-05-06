#!/usr/bin/env bash
# 원클릭 배포: Docker Compose 빌드 및 기동
# 사용: ./scripts/deploy.sh [prod]
#   prod 인자 시 docker-compose.prod.yml 오버레이 적용

set -e
cd "$(dirname "$0")/.."

COMPOSE_FILES="-f docker-compose.yml"
if [ "${1:-}" = "prod" ]; then
  COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml"
  echo "Using production overlay."
fi

if [ ! -f .env ]; then
  echo "ERROR: .env file not found. Copy .env.example to .env and set OPENAI_API_KEY etc."
  exit 1
fi

echo "Building images..."
docker compose $COMPOSE_FILES build

echo "Starting services..."
docker compose $COMPOSE_FILES up -d

echo "Waiting for API to be healthy..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "API is up."
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "WARN: API health check timed out. Check: docker compose logs api"
    exit 1
  fi
  sleep 2
done

echo ""
echo "Deployment done."
echo "  Chat UI:    http://localhost:8501"
echo "  API docs:   http://localhost:8000/docs"
echo "  Health:     http://localhost:8000/health"
echo ""
echo "To load initial data, run: ./scripts/init_data.sh"
