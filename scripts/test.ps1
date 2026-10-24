param([switch]$Postgres)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if ($Postgres) {
  foreach ($line in Get-Content -LiteralPath (Join-Path $projectRoot '.env')) {
    if ($line -match '^KYP_DATABASE_URL=(.*)$') { $env:KYP_TEST_POSTGRES_URL = $matches[1] }
  }
}
Set-Location -LiteralPath (Join-Path $projectRoot 'backend')
python -B -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Set-Location -LiteralPath (Join-Path $projectRoot 'mobile')
npm.cmd run typecheck
exit $LASTEXITCODE
