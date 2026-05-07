#Requires -Version 5.1
$ErrorActionPreference = 'SilentlyContinue'

$ROOT     = $PSScriptRoot
$PIDSFILE = Join-Path $ROOT '.pids.json'

Write-Host ""
Write-Host "  PipelineModeling — stopping workspace" -ForegroundColor Cyan
Write-Host ""

# ── Stop local services by PID ────────────────────────────────────────────────
if (Test-Path $PIDSFILE) {
    $saved = Get-Content $PIDSFILE | ConvertFrom-Json
    foreach ($svc in @('API', 'Frontend', 'Seeder')) {
        $pid = $saved.$svc
        if ($pid) {
            Write-Host "  Stopping $svc (PID $pid)..." -ForegroundColor Yellow
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        }
    }
} else {
    Write-Host "  .pids.json not found — skipping PID-based stop" -ForegroundColor Yellow
}

# ── Safety net: kill any remaining PipelineModeling terminal windows ──────────
$psxe = @('powershell', 'pwsh')
foreach ($exe in $psxe) {
    Get-Process $exe -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowTitle -match 'PipelineModeling' } |
        ForEach-Object {
            Write-Host "  Killing orphaned window: $($_.MainWindowTitle) (PID $($_.Id))" -ForegroundColor Yellow
            Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        }
}

# ── Stop Docker services ──────────────────────────────────────────────────────
Write-Host "  Stopping Prometheus + Grafana..." -ForegroundColor Yellow
docker compose `
    -f (Join-Path $ROOT 'docker-compose.yml') `
    -f (Join-Path $ROOT 'docker-compose.override.yml') `
    stop prometheus grafana 2>&1 | Out-Null

# ── Cleanup ───────────────────────────────────────────────────────────────────
Remove-Item $PIDSFILE -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "  [OK] All services stopped." -ForegroundColor Green
Write-Host ""
