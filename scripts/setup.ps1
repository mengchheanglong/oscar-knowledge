$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (!(Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
    $knowledgeTokenBytes = New-Object byte[] 32
    $knowledgeRng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $knowledgeRng.GetBytes($knowledgeTokenBytes)
    $knowledgeRng.Dispose()
    $knowledgeToken = [Convert]::ToBase64String($knowledgeTokenBytes)
    $knowledgeEnvironment = Get-Content -LiteralPath '.env' -Raw
    $knowledgeEnvironment.Replace('KNOWLEDGE_SERVICE_TOKEN=', "KNOWLEDGE_SERVICE_TOKEN=$knowledgeToken") | Set-Content -LiteralPath '.env' -Encoding utf8
}
docker compose up -d --wait postgres
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& .\.venv\Scripts\alembic.exe upgrade head
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& .\.venv\Scripts\knowledgectl.exe doctor
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& .\.venv\Scripts\knowledgectl.exe import-manifest fixtures/demo.yaml
exit $LASTEXITCODE
