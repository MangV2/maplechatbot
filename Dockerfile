# ── API/TEST 공용 베이스 ─────────────────────────────
FROM python:3.12-slim AS base

WORKDIR /app

# 시스템 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 설치 (캐시 레이어)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── API 런타임 이미지 ─────────────────────────────────
FROM base AS api

# 애플리케이션 코드 복사
COPY app/ app/
COPY scripts/ scripts/

# 비root 사용자
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# 헬스 체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ── 테스트 실행 이미지 ────────────────────────────────
FROM base AS test

COPY app/ app/
COPY tests/ tests/
COPY scripts/ scripts/

CMD ["pytest", "tests/unit", "-v"]
