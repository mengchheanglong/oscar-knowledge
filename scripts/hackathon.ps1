param([switch]$Start, [string]$Collection = 'mba-mit-demo')
$ErrorActionPreference = 'Stop'
$readinessRoot = Split-Path -Parent $PSScriptRoot
Push-Location $readinessRoot
try {
    if ($Start) {
        try { Invoke-RestMethod http://127.0.0.1:11434/api/version -TimeoutSec 2 | Out-Null }
        catch { Start-Process -FilePath 'D:\Apps\Ollama\ollama app.exe' -WindowStyle Hidden }
        & (Join-Path $PSScriptRoot 'warmup-ollama.ps1')
        if ($LASTEXITCODE) { Write-Warning 'Ollama warmup unavailable; normal chat can still run.' }
        & docker compose up -d --wait postgres
        if ($LASTEXITCODE) { throw 'Knowledge database unavailable' }
        & .\.venv\Scripts\alembic.exe upgrade head
        if ($LASTEXITCODE) { throw 'Knowledge migration unavailable; data preserved' }
        & docker compose --profile app up -d --build --wait api
        if ($LASTEXITCODE) { throw 'Knowledge API unavailable' }
        & (Join-Path (Split-Path $readinessRoot -Parent) 'oscar-backend\scripts\start-local.ps1') -SkipAgents
        if ($LASTEXITCODE) { throw 'OSCAR startup needs attention' }
    }
    & .\.venv\Scripts\python.exe scripts/readiness.py --collection $Collection --output data/evaluations/readiness.json
    exit $LASTEXITCODE
} finally { Pop-Location }
