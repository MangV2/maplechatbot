# ── Streamlit 프론트엔드 Dockerfile ──────────────────
FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 설치
RUN pip install --no-cache-dir \
    streamlit>=1.30.0 \
    httpx>=0.27.0

# 프론트엔드 코드 복사
COPY . .

# 비root 사용자
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Streamlit 설정
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address", "0.0.0.0"]
