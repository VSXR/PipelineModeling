#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── Paths ─────────────────────────────────────────────────────────────────────
$ROOT      = $PSScriptRoot
$VENV      = Join-Path $ROOT '.venv\Scripts'
$UVICORN   = Join-Path $VENV  'uvicorn.exe'
$STREAMLIT = Join-Path $VENV  'streamlit.exe'
$PYTHON    = Join-Path $VENV  'python.exe'
$PIDSFILE  = Join-Path $ROOT  '.pids.json'
$psExe     = if (Get-Command pwsh -ErrorAction SilentlyContinue) { 'pwsh' } else { 'powershell' }

# ── Output helpers ────────────────────────────────────────────────────────────
function Write-Step([string]$msg) { Write-Host "  >> $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Write-Fail([string]$msg) {
    Write-Host "`n  [FAIL] $msg" -ForegroundColor Red
    exit 1
}

# ── Port check ────────────────────────────────────────────────────────────────
function Test-PortInUse([int]$port) {
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect('127.0.0.1', $port)
        $tcp.Close()
        return $true
    } catch {
        return $false
    }
}

# ── Prerequisites ─────────────────────────────────────────────────────────────
function Assert-Prerequisites {
    Write-Step "Checking prerequisites..."

    if (-not (Test-Path (Join-Path $ROOT '.venv'))) {
        Write-Fail ".venv not found. Create it first:`n  python -m venv .venv`n  .venv\Scripts\pip install -r services/api/requirements.txt -r services/frontend/requirements.txt -r services/seeder/requirements.txt"
    }

    docker info 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Docker Desktop is not running. Start it and try again."
    }

    Write-Ok "Prerequisites OK (.venv found, Docker running)"
}

# ── Port conflicts ────────────────────────────────────────────────────────────
function Invoke-PortChecks {
    $conflicts = @()
    @{ API = 8000; Frontend = 8501; Prometheus = 9090; Grafana = 3000 }.GetEnumerator() | ForEach-Object {
        if (Test-PortInUse $_.Value) { $conflicts += "$($_.Key):$($_.Value)" }
    }
    if ($conflicts.Count -gt 0) {
        Write-Warn "Ports already in use: $($conflicts -join ', ')"
        $ans = Read-Host "  Continue anyway? [y/N]"
        if ($ans -notmatch '^[yY]$') { exit 0 }
    }
}

# ── .env setup ────────────────────────────────────────────────────────────────
function Initialize-DotEnv {
    $envFile = Join-Path $ROOT '.env'
    if (-not (Test-Path $envFile)) {
        Copy-Item (Join-Path $ROOT '.env.example') $envFile
        Write-Ok "Created .env from .env.example"
    } else {
        Write-Ok ".env already exists"
    }
}

# ── Model bootstrap ───────────────────────────────────────────────────────────
function Invoke-ModelBootstrap {
    $modelFile = Join-Path $ROOT 'model\weights\model.pkl'
    if (-not (Test-Path $modelFile)) {
        Write-Step "model.pkl not found — running model/train.py..."
        $proc = Start-Process -FilePath $PYTHON `
            -ArgumentList (Join-Path $ROOT 'model\train.py') `
            -WorkingDirectory $ROOT `
            -Wait -PassThru -NoNewWindow
        if ($proc.ExitCode -ne 0) {
            Write-Fail "model/train.py failed (exit $($proc.ExitCode))"
        }
        Write-Ok "Model trained and saved to model/weights/model.pkl"
    } else {
        Write-Ok "model.pkl exists"
    }
}

# ── Docker infra ──────────────────────────────────────────────────────────────
function Start-DockerServices {
    Write-Step "Starting Prometheus + Grafana via Docker Compose..."
    docker compose `
        -f (Join-Path $ROOT 'docker-compose.yml') `
        -f (Join-Path $ROOT 'docker-compose.override.yml') `
        up -d prometheus grafana 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "docker compose failed. Check Docker Desktop and try again."
    }
    Write-Ok "Prometheus :9090 and Grafana :3000 started"
}

# ── Service window launcher ───────────────────────────────────────────────────
function Start-ServiceWindow([string]$title, [string]$cmd) {
    $bytes   = [System.Text.Encoding]::Unicode.GetBytes($cmd)
    $encoded = [Convert]::ToBase64String($bytes)
    $proc = Start-Process $psExe `
        -ArgumentList "-NoExit", "-EncodedCommand", $encoded `
        -PassThru
    return $proc.Id
}

# ── API health poll ───────────────────────────────────────────────────────────
function Wait-ForApiHealth {
    Write-Step "Waiting for API at http://localhost:8000/health (up to 60s)..."
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri 'http://localhost:8000/health' `
                -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            if ($r.StatusCode -eq 200) {
                Write-Ok "API is healthy"
                return
            }
        } catch { }
        Start-Sleep -Seconds 2
    }
    Write-Fail "API did not become healthy within 60s. Check the API window for errors."
}

# ── Summary ───────────────────────────────────────────────────────────────────
function Write-Summary {
    Write-Host ""
    Write-Host "  =============================================" -ForegroundColor Green
    Write-Host "   PipelineModeling workspace is running" -ForegroundColor Green
    Write-Host "  =============================================" -ForegroundColor Green
    Write-Host "   API (Swagger)   http://localhost:8000/docs"
    Write-Host "   API Health      http://localhost:8000/health"
    Write-Host "   Frontend        http://localhost:8501"
    Write-Host "   Prometheus      http://localhost:9090"
    Write-Host "   Grafana         http://localhost:3000  (admin / see .env)"
    Write-Host "  =============================================" -ForegroundColor Green
    Write-Host "   PIDs saved to .pids.json"
    Write-Host "   Run .\stop.ps1 to shut everything down"
    Write-Host "  =============================================" -ForegroundColor Green
    Write-Host ""
}

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

Write-Host ""
Write-Host "  PipelineModeling — starting workspace" -ForegroundColor Cyan
Write-Host ""

Assert-Prerequisites
Invoke-PortChecks
Initialize-DotEnv
Invoke-ModelBootstrap
Start-DockerServices

# ── API window ────────────────────────────────────────────────────────────────
$apiCmd = @"
`$host.UI.RawUI.WindowTitle = 'PipelineModeling - API'
`$env:MODEL_PATH      = '$ROOT\model\weights\model.pkl'
`$env:GIT_REPO_PATH   = '$ROOT'
`$env:DVC_REMOTE_PATH = '$ROOT\dvc-remote'
Set-Location '$ROOT\services\api'
& '$UVICORN' main:app --reload --port 8000 --log-level info
"@

Write-Step "Starting API (uvicorn)..."
$apiPid = Start-ServiceWindow "API" $apiCmd

Wait-ForApiHealth

# ── Frontend window ───────────────────────────────────────────────────────────
$frontendCmd = @"
`$host.UI.RawUI.WindowTitle = 'PipelineModeling - Frontend'
`$env:API_URL     = 'http://localhost:8000'
`$env:GRAFANA_URL = 'http://localhost:3000'
& '$STREAMLIT' run '$ROOT\services\frontend\app.py' --server.port 8501 --server.headless true
"@

Write-Step "Starting Frontend (Streamlit)..."
$frontendPid = Start-ServiceWindow "Frontend" $frontendCmd

# ── Seeder window ─────────────────────────────────────────────────────────────
$seederCmd = @"
`$host.UI.RawUI.WindowTitle = 'PipelineModeling - Seeder'
`$env:API_URL               = 'http://localhost:8000'
`$env:REQUESTS_PER_SECOND   = '20'
`$env:INFERENCE_CONCURRENCY = '10'
`$env:TRAINING_INTERVAL_S   = '30'
`$env:TRAINING_BATCH_SIZE   = '50'
`$env:DRIFT_ONSET_AFTER_S   = '120'
`$env:DRIFT_MAGNITUDE       = '2.0'
& '$PYTHON' '$ROOT\services\seeder\seeder.py'
"@

Write-Step "Starting Seeder..."
$seederPid = Start-ServiceWindow "Seeder" $seederCmd

# ── Save PIDs ─────────────────────────────────────────────────────────────────
@{ API = $apiPid; Frontend = $frontendPid; Seeder = $seederPid } |
    ConvertTo-Json | Set-Content $PIDSFILE

Write-Ok "PIDs saved to .pids.json (API=$apiPid, Frontend=$frontendPid, Seeder=$seederPid)"

Write-Summary
