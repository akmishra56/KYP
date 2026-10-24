param([switch]$SQLite, [int]$Port = 8001)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $SQLite) {
  $environmentFile = Join-Path $projectRoot '.env'
  if (-not (Test-Path -LiteralPath $environmentFile)) { throw 'Copy .env.example to .env and set local credentials first.' }
  foreach ($line in Get-Content -LiteralPath $environmentFile) {
    if ($line -match '^([A-Z_]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') }
  }
  docker compose --project-directory $projectRoot up -d --wait
  if ($LASTEXITCODE -ne 0) { throw 'Database startup failed.' }
} else {
  Remove-Item Env:KYP_DATABASE_URL -ErrorAction SilentlyContinue
}
Set-Location -LiteralPath (Join-Path $projectRoot 'backend')
python -B -m uvicorn kyp.api:app --host 127.0.0.1 --port $Port
