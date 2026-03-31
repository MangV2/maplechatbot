Param(
    [ValidateSet("smoke", "unit", "all")]
    [string]$Mode = "smoke",
    [switch]$NoBuild,
    [switch]$NoUp,
    [switch]$DownAfter
)

$ErrorActionPreference = "Stop"

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)][string]$Title,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )
    Write-Host ""
    Write-Host "==> $Title" -ForegroundColor Cyan
    & $Action
}

Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path ".env")) {
    throw ".env 파일이 없습니다. .env.example 복사 후 값(OPENAI_API_KEY 등)을 채워주세요."
}

if (-not $NoBuild) {
    Invoke-Step -Title "Docker 이미지 빌드" -Action {
        docker compose -f docker-compose.yml -f docker-compose.test.yml build api test
    }
}

if (-not $NoUp) {
    Invoke-Step -Title "의존 서비스 기동" -Action {
        docker compose -f docker-compose.yml -f docker-compose.test.yml up -d qdrant postgres api
    }
}

Invoke-Step -Title "API 헬스체크 대기" -Action {
    $healthy = $false
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $resp = Invoke-WebRequest "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 3
            if ($resp.StatusCode -eq 200) {
                $healthy = $true
                break
            }
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    if (-not $healthy) {
        throw "API 헬스체크 타임아웃. 'docker compose logs api'로 확인하세요."
    }
}

$pytestArgs = switch ($Mode) {
    "smoke" { "tests/unit/test_rag_router.py tests/unit/test_agent_router.py -v" }
    "unit" { "tests/unit -v" }
    "all" { "tests -v --cov=app" }
}

Invoke-Step -Title "테스트 실행 (mode=$Mode)" -Action {
    docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test sh -lc "pytest $pytestArgs"
}

if ($DownAfter) {
    Invoke-Step -Title "서비스 종료" -Action {
        docker compose -f docker-compose.yml -f docker-compose.test.yml down
    }
}

Write-Host ""
Write-Host "Done: Docker tests (mode=$Mode)" -ForegroundColor Green
