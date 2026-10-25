param([int]$WaitSeconds = 120)
$ErrorActionPreference = 'Stop'
$qwenLogRoot = 'D:\AI\Ollama\logs'
New-Item -ItemType Directory -Force -Path $qwenLogRoot | Out-Null
try {
    $qwenDeadline = (Get-Date).AddSeconds($WaitSeconds)
    do {
        try {
            $qwenVersion = Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 2
            break
        } catch {
            if ((Get-Date) -ge $qwenDeadline) { throw 'Local Ollama is unavailable' }
            Start-Sleep -Seconds 2
        }
    } while ($true)
    $qwenBody = @{model='qwen3-embedding:0.6b';input=@('Local embedding runtime warmup.');truncate=$false;keep_alive='-1m';options=@{num_ctx=4096}} | ConvertTo-Json -Compress
    $qwenResult = Invoke-RestMethod 'http://127.0.0.1:11434/api/embed' -Method Post -ContentType application/json -Body $qwenBody -TimeoutSec 180
    if ($qwenResult.embeddings.Count -ne 1 -or $qwenResult.embeddings[0].Count -ne 1024) { throw 'Unexpected vector dimensions' }
    'PASS: local qwen3-embedding:0.6b warm, 1024 dimensions' | Set-Content -LiteralPath (Join-Path $qwenLogRoot 'warmup.log')
    Write-Output 'PASS: local qwen3-embedding:0.6b warm, 1024 dimensions'
} catch {
    'WARMUP_FAILED: check the Ollama tray app and local model. No source text or credentials logged.' | Set-Content -LiteralPath (Join-Path $qwenLogRoot 'warmup.log')
    Write-Warning 'Qwen warmup unavailable; keyword retrieval and normal OSCAR chat remain available.'
    exit 1
}
