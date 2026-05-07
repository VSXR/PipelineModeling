#Requires -Version 5.1
<#
.SYNOPSIS
    PipelineModeling — CLI de gestion del workspace.

.DESCRIPTION
    Punto de entrada unificado para todas las operaciones del proyecto.

.PARAMETER Command
    setup   — primera configuracion (venv, deps, .env, modelo inicial)
    start   — arranca API, Frontend, Seeder + Prometheus/Grafana en Docker
    stop    — para todos los servicios
    status  — muestra el estado de los servicios y la version del modelo activa
    test    — ejecuta la suite de integracion (requiere API corriendo)
    train   — entrena una nueva version del modelo y la versiona con DVC + Git

.EXAMPLE
    .\pipeline.ps1 setup
    .\pipeline.ps1 start
    .\pipeline.ps1 stop
    .\pipeline.ps1 status
    .\pipeline.ps1 test
    .\pipeline.ps1 train -Version v1.3.0 -NSamples 8000
    .\pipeline.ps1 train -Version v1.4.0 -NSamples 10000 -RandomState 7
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)][string]$Command     = 'help',
    [string]$Version      = '',
    [int]$RandomState     = 0,
    [ValidateSet('local','minio')][string]$Remote = 'local'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── Rutas ─────────────────────────────────────────────────────────────────────
$ROOT      = $PSScriptRoot
$VENV      = Join-Path $ROOT '.venv\Scripts'
$UVICORN   = Join-Path $VENV  'uvicorn.exe'
$STREAMLIT = Join-Path $VENV  'streamlit.exe'
$PYTHON    = Join-Path $VENV  'python.exe'
$PYTEST    = Join-Path $VENV  'pytest.exe'
$DVC       = Join-Path $VENV  'dvc.exe'
$PIP       = Join-Path $VENV  'pip.exe'
$TRAIN     = Join-Path $ROOT  'model\train.py'
$PIDSFILE  = Join-Path $ROOT  '.pids.json'
$psExe     = if (Get-Command pwsh -ErrorAction SilentlyContinue) { 'pwsh' } else { 'powershell' }

# ── Helpers de salida ─────────────────────────────────────────────────────────
function Write-Header([string]$msg) { Write-Host "`n  $msg" -ForegroundColor Cyan }
function Write-Step  ([string]$msg) { Write-Host "  >> $msg" -ForegroundColor Cyan }
function Write-Ok    ([string]$msg) { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn  ([string]$msg) { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Write-Fail  ([string]$msg) { Write-Host "`n  [FAIL] $msg`n" -ForegroundColor Red; exit 1 }
function Write-Info  ([string]$msg) { Write-Host "  $msg" }

# ── Utilidades ────────────────────────────────────────────────────────────────
function Test-PortInUse([int]$port) {
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect('127.0.0.1', $port)
        $tcp.Close()
        return $true
    } catch { return $false }
}

function Test-ApiHealth {
    try {
        $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' `
            -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        return $r.StatusCode -eq 200
    } catch { return $false }
}

function Start-ServiceWindow([string]$cmd) {
    $bytes   = [System.Text.Encoding]::Unicode.GetBytes($cmd)
    $encoded = [Convert]::ToBase64String($bytes)
    $proc    = Start-Process $psExe -ArgumentList '-NoExit', '-EncodedCommand', $encoded -PassThru
    return $proc.Id
}

# ══════════════════════════════════════════════════════════════════════════════
#  SETUP — primera configuracion
# ══════════════════════════════════════════════════════════════════════════════
function Invoke-Setup {
    Write-Header "PipelineModeling — setup"

    # Python
    Write-Step "Verificando Python..."
    $pyVersion = python --version 2>&1
    if ($LASTEXITCODE -ne 0) { Write-Fail "Python no encontrado. Instala Python 3.11+." }
    Write-Ok $pyVersion

    # .venv
    Write-Step "Creando entorno virtual .venv..."
    if (Test-Path (Join-Path $ROOT '.venv')) {
        Write-Ok ".venv ya existe"
    } else {
        python -m venv (Join-Path $ROOT '.venv') | Out-Null
        Write-Ok ".venv creado"
    }

    # dependencias
    Write-Step "Instalando dependencias..."
    $reqs = @(
        'services/api/requirements.txt',
        'services/frontend/requirements.txt',
        'services/seeder/requirements.txt',
        'model/requirements.txt',
        'tests/requirements.txt'
    )
    foreach ($req in $reqs) {
        $path = Join-Path $ROOT $req
        if (Test-Path $path) {
            & $PIP install -r $path -q 2>&1 | Where-Object { $_ -notmatch "does not provide the extra 'boto3'" } | Out-Null
            Write-Ok $req
        }
    }

    # pathspec compatible con DVC
    Write-Step "Asegurando compatibilidad pathspec/DVC..."
    & $PIP install "pathspec<0.12" -q
    Write-Ok "pathspec<0.12 instalado"

    # .env
    Write-Step "Configurando .env..."
    $envFile = Join-Path $ROOT '.env'
    if (-not (Test-Path $envFile)) {
        Copy-Item (Join-Path $ROOT '.env.example') $envFile
        Write-Ok ".env creado desde .env.example"
    } else {
        Write-Ok ".env ya existe"
    }

    # Docker
    Write-Step "Verificando Docker..."
    docker info 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Warn "Docker Desktop no esta corriendo. Necesario para Prometheus y Grafana." }
    else { Write-Ok "Docker OK" }

    # Modelo inicial
    Write-Step "Verificando modelo inicial..."
    $modelFile = Join-Path $ROOT 'model\weights\model.pkl'
    if (-not (Test-Path $modelFile)) {
        Write-Step "Entrenando modelo inicial..."
        $proc = Start-Process -FilePath $PYTHON -ArgumentList $TRAIN `
            -WorkingDirectory $ROOT -Wait -PassThru -NoNewWindow
        if ($proc.ExitCode -ne 0) { Write-Fail "Fallo el entrenamiento inicial." }
        Write-Ok "Modelo inicial entrenado"
    } else {
        Write-Ok "model.pkl ya existe"
    }

    Write-Host ""
    Write-Host "  =============================================" -ForegroundColor Green
    Write-Host "  Setup completado. Siguiente paso:" -ForegroundColor Green
    Write-Host "    .\pipeline.ps1 start" -ForegroundColor White
    Write-Host "  =============================================" -ForegroundColor Green
    Write-Host ""
}

# ══════════════════════════════════════════════════════════════════════════════
#  START
# ══════════════════════════════════════════════════════════════════════════════
function Invoke-Start {
    Write-Header "PipelineModeling — start"

    # Prerrequisitos
    Write-Step "Verificando prerrequisitos..."
    if (-not (Test-Path (Join-Path $ROOT '.venv'))) {
        Write-Fail ".venv no encontrado. Ejecuta primero: .\pipeline.ps1 setup"
    }
    docker info 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Fail "Docker Desktop no esta corriendo." }
    Write-Ok "Prerrequisitos OK"

    # Puertos
    $conflicts = @()
    @{ API = 8000; Frontend = 8501; Prometheus = 9090; Grafana = 3000 }.GetEnumerator() |
        ForEach-Object { if (Test-PortInUse $_.Value) { $conflicts += "$($_.Key):$($_.Value)" } }
    if ($conflicts.Count -gt 0) {
        Write-Warn "Puertos en uso: $($conflicts -join ', ')"
        $ans = Read-Host "  Continuar de todas formas? [y/N]"
        if ($ans -notmatch '^[yY]$') { exit 0 }
    }

    # .env
    $envFile = Join-Path $ROOT '.env'
    if (-not (Test-Path $envFile)) {
        Copy-Item (Join-Path $ROOT '.env.example') $envFile
        Write-Ok "Creado .env desde .env.example"
    }

    # Modelo
    $modelFile = Join-Path $ROOT 'model\weights\model.pkl'
    if (-not (Test-Path $modelFile)) {
        Write-Step "Entrenando modelo inicial..."
        $proc = Start-Process -FilePath $PYTHON -ArgumentList $TRAIN `
            -WorkingDirectory $ROOT -Wait -PassThru -NoNewWindow
        if ($proc.ExitCode -ne 0) { Write-Fail "Fallo el entrenamiento inicial." }
        Write-Ok "Modelo inicial entrenado"
    }

    # Docker (MinIO + Prometheus + Grafana)
    Write-Step "Arrancando MinIO + Prometheus + Grafana..."
    docker compose `
        -f (Join-Path $ROOT 'docker-compose.yml') `
        -f (Join-Path $ROOT 'docker-compose.override.yml') `
        up -d minio minio-init prometheus grafana 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Fail "docker compose fallo." }
    Write-Ok "MinIO :9000/:9001, Prometheus :9090, Grafana :3000 arrancados"

    # API
    $apiCmd = @"
`$host.UI.RawUI.WindowTitle = 'PipelineModeling - API'
`$env:MODEL_PATH      = '$ROOT\model\weights\model.pkl'
`$env:GIT_REPO_PATH   = '$ROOT'
`$env:DVC_REMOTE_PATH = '$ROOT\dvc-remote'
Set-Location '$ROOT\services\api'
& '$UVICORN' main:app --reload --port 8000 --log-level info
"@
    Write-Step "Arrancando API (uvicorn --reload)..."
    $apiPid = Start-ServiceWindow $apiCmd

    # Healthcheck
    Write-Step "Esperando a que la API este sana (hasta 60s)..."
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        if (Test-ApiHealth) { Write-Ok "API lista"; break }
        Start-Sleep -Seconds 2
    }
    if (-not (Test-ApiHealth)) { Write-Fail "La API no respondio en 60s. Revisa la ventana API." }

    # Frontend
    $frontendCmd = @"
`$host.UI.RawUI.WindowTitle = 'PipelineModeling - Frontend'
`$env:API_URL     = 'http://localhost:8000'
`$env:GRAFANA_URL = 'http://localhost:3000'
& '$STREAMLIT' run '$ROOT\services\frontend\app.py' --server.port 8501 --server.headless true
"@
    Write-Step "Arrancando Frontend (Streamlit)..."
    $frontendPid = Start-ServiceWindow $frontendCmd

    # Seeder
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
    Write-Step "Arrancando Seeder..."
    $seederPid = Start-ServiceWindow $seederCmd

    # PIDs
    @{ API = $apiPid; Frontend = $frontendPid; Seeder = $seederPid } |
        ConvertTo-Json | Set-Content $PIDSFILE

    Write-Host ""
    Write-Host "  =============================================" -ForegroundColor Green
    Write-Host "   PipelineModeling workspace activo" -ForegroundColor Green
    Write-Host "  =============================================" -ForegroundColor Green
    Write-Info "   Frontend     http://localhost:8501"
    Write-Info "   API (Swagger) http://localhost:8000/docs"
    Write-Info "   API Health    http://localhost:8000/health"
    Write-Info "   Prometheus    http://localhost:9090"
    Write-Info "   Grafana       http://localhost:3000  (admin / ver .env)"
    Write-Host "  =============================================" -ForegroundColor Green
    Write-Info "   Parar: .\pipeline.ps1 stop"
    Write-Host "  =============================================" -ForegroundColor Green
    Write-Host ""
}

# ══════════════════════════════════════════════════════════════════════════════
#  STOP
# ══════════════════════════════════════════════════════════════════════════════
function Invoke-Stop {
    $ErrorActionPreference = 'SilentlyContinue'
    Write-Header "PipelineModeling — stop"

    # Ensure any process listening on project ports is stopped (idempotent)
    $ports = 3000,8000,8501,9000,9001,9090
    foreach ($port in $ports) {
        Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique |
            ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
    }

    if (Test-Path $PIDSFILE) {
        $saved = Get-Content $PIDSFILE | ConvertFrom-Json
        foreach ($svc in @('API', 'Frontend', 'Seeder')) {
            $pid = $saved.$svc
            if ($pid) {
                Write-Step "Parando $svc (PID $pid)..."
                Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            }
        }
    } else {
        Write-Warn ".pids.json no encontrado — saltando stop por PID"
    }

    foreach ($exe in @('powershell', 'pwsh')) {
        Get-Process $exe -ErrorAction SilentlyContinue |
            Where-Object { $_.MainWindowTitle -match 'PipelineModeling' -and $_.Id -ne $PID } |
            ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
    }

    Write-Step "Parando contenedores Docker..."
    docker compose `
        -f (Join-Path $ROOT 'docker-compose.yml') `
        -f (Join-Path $ROOT 'docker-compose.override.yml') `
        stop prometheus grafana minio 2>&1 | Out-Null

    Remove-Item $PIDSFILE -ErrorAction SilentlyContinue

    Write-Ok "Todos los servicios parados."
    Write-Host ""
}

# ══════════════════════════════════════════════════════════════════════════════
#  STATUS
# ══════════════════════════════════════════════════════════════════════════════
function Invoke-Status {
    Write-Header "PipelineModeling — status"
    Write-Host ""

    # Procesos locales
    $savedPids = $null
    if (Test-Path $PIDSFILE) {
        $savedPids = Get-Content $PIDSFILE | ConvertFrom-Json
    }

    foreach ($svc in @('API', 'Frontend', 'Seeder')) {
        $pidVal = if ($savedPids) { $savedPids.$svc } else { $null }
        if ($pidVal) {
            $running = Get-Process -Id $pidVal -ErrorAction SilentlyContinue
            $state   = if ($running) { "[RUNNING]" } else { "[STOPPED]" }
            $color   = if ($running) { 'Green' } else { 'Red' }
            Write-Host ("  {0,-12} PID {1,-8} {2}" -f $svc, $pidVal, $state) -ForegroundColor $color
        } else {
            Write-Host ("  {0,-12} {1}" -f $svc, "[NO PID]") -ForegroundColor Yellow
        }
    }

    # API health + version
    Write-Host ""
    if (Test-ApiHealth) {
        try {
            $health = Invoke-RestMethod 'http://127.0.0.1:8000/health' -TimeoutSec 3
            Write-Host "  API Health    [OK] model_loaded=$($health.model_loaded)  version=$($health.model_version)" -ForegroundColor Green
        } catch {
            Write-Host "  API Health    [OK]" -ForegroundColor Green
        }
    } else {
        Write-Host "  API Health    [UNREACHABLE]" -ForegroundColor Red
    }

    # Docker
    Write-Host ""
    $containers = @('prometheus', 'grafana', 'pipeline_minio')
    foreach ($c in $containers) {
        $state = docker inspect --format='{{.State.Status}}' $c 2>$null
        $ok    = $LASTEXITCODE -eq 0 -and $state -eq 'running'
        if ($ok) {
            Write-Host ("  {0,-14} [RUNNING]" -f $c) -ForegroundColor Green
        } else {
            Write-Host ("  {0,-14} [STOPPED]" -f $c) -ForegroundColor Yellow
        }
    }

    Write-Host ""
}

# ══════════════════════════════════════════════════════════════════════════════
#  TEST
# ══════════════════════════════════════════════════════════════════════════════
function Invoke-Tests {
    Write-Header "PipelineModeling — test"

    if (-not (Test-Path $PYTEST)) {
        Write-Fail "pytest no encontrado. Ejecuta: .\pipeline.ps1 setup"
    }
    if (-not (Test-ApiHealth)) {
        Write-Fail "La API no esta disponible en http://localhost:8000. Ejecuta: .\pipeline.ps1 start"
    }

    Write-Step "Ejecutando suite de tests..."
    Write-Host ""
    & $PYTEST (Join-Path $ROOT 'tests') -v --tb=short
    $code = $LASTEXITCODE

    Write-Host ""
    if ($code -eq 0) { Write-Ok "Todos los tests pasaron." }
    else             { Write-Fail "Algunos tests fallaron (exit code $code)." }
}

# ══════════════════════════════════════════════════════════════════════════════
#  TRAIN
# ══════════════════════════════════════════════════════════════════════════════
function Invoke-Train {
    Write-Header "PipelineModeling — train $Version"

    if (-not $Version) { Write-Fail "Especifica -Version (ej: -Version v1.3.0)" }
    if ($Version -notmatch '^v\d+\.\d+\.\d+$') {
        Write-Fail "Formato incorrecto. Usa vX.Y.Z (ej: v1.3.0)"
    }
    $existsLocal = git tag -l $Version
    if ($existsLocal) { Write-Fail "El tag $Version ya existe localmente." }

    # Actualizar parametros
    Write-Step "Actualizando parametros en model/train.py..."
    $content = Get-Content $TRAIN -Raw
    if ($RandomState -gt 0) {
        $content = $content -replace 'RANDOM_STATE\s*=\s*\d+', "RANDOM_STATE = $RandomState"
        Write-Ok "RANDOM_STATE = $RandomState"
    } else {
        Write-Warn "Sin parametros nuevos — DVC puede usar cache si nada cambio. Pasa -RandomState <int> diferente."
    }
    Set-Content -Path $TRAIN -Value $content -NoNewline

    # dvc repro
    Write-Step "dvc repro..."
    $reproOut = & $DVC repro 2>&1
    $reproOut | ForEach-Object { Write-Info "  $_" }
    if ($LASTEXITCODE -ne 0) { Write-Fail "dvc repro fallo." }
    if ($reproOut -match 'is cached') {
        Write-Fail "DVC uso cache — el modelo no cambio. Pasa -NSamples o -RandomState diferentes."
    }
    Write-Ok "Pipeline ejecutado, dvc.lock actualizado"

    # dvc push
    Write-Step "dvc push --remote $Remote..."
    & $DVC push --remote $Remote 2>&1 | ForEach-Object { Write-Info "  $_" }
    if ($LASTEXITCODE -ne 0) { Write-Fail "dvc push --remote $Remote fallo." }
    Write-Ok "Artefacto subido al remote '$Remote'"

    # git commit
    Write-Step "git commit..."
    $metricsFile = Join-Path $ROOT 'model\metrics.json'
    $metrics     = if (Test-Path $metricsFile) { Get-Content $metricsFile | ConvertFrom-Json } else { @{} }
    $acc = if ($metrics.accuracy) { $metrics.accuracy } else { '?' }
    $f1  = if ($metrics.f1)       { $metrics.f1 }       else { '?' }

    git add "dvc.lock" "model/metrics.json" "model/train.py" 2>&1 | Out-Null
    $staged = git diff --cached --name-only
    if (-not $staged) { Write-Fail "Nada que commitear. El modelo no cambio realmente." }

    $msg = "train: model $Version (accuracy=$acc, f1=$f1)"
    git commit -m $msg 2>&1 | ForEach-Object { Write-Info "  $_" }
    if ($LASTEXITCODE -ne 0) { Write-Fail "git commit fallo." }
    Write-Ok "Commit: $msg"

    # git tag + push
    Write-Step "git tag $Version + git push..."
    git tag $Version 2>&1 | Out-Null
    git push origin develop --tags 2>&1 | ForEach-Object { Write-Info "  $_" }
    if ($LASTEXITCODE -ne 0) { Write-Fail "git push fallo." }
    Write-Ok "Tag $Version publicado en GitHub"

    Write-Host ""
    Write-Host "  =============================================" -ForegroundColor Green
    Write-Host "  Modelo $Version publicado" -ForegroundColor Green
    Write-Host "  accuracy : $acc" -ForegroundColor Green
    Write-Host "  f1       : $f1" -ForegroundColor Green
    Write-Host "  =============================================" -ForegroundColor Green
    Write-Host ""
}

# ══════════════════════════════════════════════════════════════════════════════
#  HELP
# ══════════════════════════════════════════════════════════════════════════════
function Show-Help {
    Write-Host ""
    Write-Host "  PipelineModeling CLI" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Uso:"
    Write-Host "    .\pipeline.ps1 <comando> [opciones]"
    Write-Host ""
    Write-Host "  Comandos:"
    Write-Host "    setup              Primera configuracion (venv, deps, .env, modelo)"
    Write-Host "    start              Arranca todo el workspace"
    Write-Host "    stop               Para todos los servicios"
    Write-Host "    status             Estado de los servicios y version del modelo"
    Write-Host "    test               Ejecuta la suite de tests de integracion"
    Write-Host "    train              Entrena y versiona un nuevo modelo"
    Write-Host ""
    Write-Host "  Opciones de train:"
    Write-Host "    -Version <vX.Y.Z>        Tag semantico (obligatorio)"
    Write-Host "    -RandomState <int>        Nuevo valor de RANDOM_STATE en train.py"
    Write-Host "    -Remote <local|minio>     Remote DVC destino (default: local)"
    Write-Host ""
    Write-Host "  Ejemplos:"
    Write-Host "    .\pipeline.ps1 setup"
    Write-Host "    .\pipeline.ps1 start"
    Write-Host "    .\pipeline.ps1 train -Version v2.0.0 -RandomState 99"
    Write-Host "    .\pipeline.ps1 train -Version v2.1.0 -RandomState 7 -Remote minio"
    Write-Host "    .\pipeline.ps1 stop"
    Write-Host ""
}

# ══════════════════════════════════════════════════════════════════════════════
#  DISPATCH
# ══════════════════════════════════════════════════════════════════════════════
switch ($Command.ToLower()) {
    'setup'  { Invoke-Setup }
    'start'  { Invoke-Start }
    'stop'   { Invoke-Stop }
    'status' { Invoke-Status }
    'test'   { Invoke-Tests }
    'train'  { Invoke-Train }
    'help'   { Show-Help }
    default  { Write-Fail "Comando desconocido: '$Command'. Usa: .\pipeline.ps1 help" }
}
