param([string]$Python = "uv")
$ErrorActionPreference = "Stop"
& $Python sync --locked
if ($LASTEXITCODE -ne 0) { throw "locked setup failed" }
Write-Output "Windows setup dependencies are ready; run: uv run mycard-benefits --demo --no-browser"
