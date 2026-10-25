$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$knowledgePreviousTestUrl = $env:KNOWLEDGE_TEST_DATABASE_URL
$knowledgePreviousUrl = $env:KNOWLEDGE_DATABASE_URL
$knowledgeResult = 1
try {
    $env:KNOWLEDGE_TEST_DATABASE_URL = 'postgresql+psycopg://knowledge_test:local_knowledge_test_only@127.0.0.1:43115/knowledge_test'
    $env:KNOWLEDGE_DATABASE_URL = $env:KNOWLEDGE_TEST_DATABASE_URL
    docker compose --profile test up -d --wait postgres-test
    if ($LASTEXITCODE) { throw 'Knowledge test database did not start' }
    & .\.venv\Scripts\alembic.exe upgrade head
    if ($LASTEXITCODE) { throw 'Knowledge test migration failed' }
    & .\.venv\Scripts\pytest.exe @args
    $knowledgeResult = $LASTEXITCODE
} finally {
    $env:KNOWLEDGE_TEST_DATABASE_URL = $knowledgePreviousTestUrl
    $env:KNOWLEDGE_DATABASE_URL = $knowledgePreviousUrl
}
exit $knowledgeResult
