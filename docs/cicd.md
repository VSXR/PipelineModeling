# CI/CD — PipelineModeling

## Flujo completo

```
commit → master
    │
    ├─► ci.yml          (siempre)              — lint + tests unitarios
    │
    └─► ct.yml          (solo si cambia model/) — entrenamiento continuo
            │  job: train   →  entrena + promueve + crea release
            └─ job: deploy  →  llama cd.yml via workflow_call
                                    │
                                    ├─ job: build-push  — build Docker + push GHCR
                                    └─ job: smoke-test  — valida /health e /infer/
```

`ci.yml` se dispara en cada push; `ct.yml` solo cuando cambia `model/`; `cd.yml` se encadena como reusable workflow desde el job `deploy` de `ct.yml`. El encadenamiento es directo (workflow_call) porque los releases creados con `GITHUB_TOKEN` no disparan eventos `on: release` en otros workflows.

---

## Workflows

### `ci.yml` — Lint y tests en cada commit

**Trigger:** push a `master` o `develop`, PR hacia `master`.

**Pasos:**
1. `ruff check model/ services/ tests/` — linter estático
2. `pytest tests/ -k "not TestAPIEndpoints and not TestObservabilityStack"` — tests unitarios sin infra

**Falla si:** el linter reporta errores o algún test unitario rompe.

---

### `ct.yml` — Continuous Training

**Trigger:**
- Push a `master` que modifique cualquier fichero bajo `model/`
- `workflow_dispatch` (manual)

**Runner:** `self-hosted` (Windows, ver sección runner más abajo). El runner debe estar en estado Idle antes de disparar este workflow.

**Secretos necesarios:**

| Secreto | Descripción |
|---|---|
| `MLFLOW_TRACKING_URI` | URI del servidor MLflow — `http://localhost:5000` para runner local |
| `MLFLOW_TRACKING_USERNAME` | Usuario de autenticación básica MLflow |
| `MLFLOW_TRACKING_PASSWORD` | Contraseña de autenticación básica MLflow |
| `GITHUB_TOKEN` | Automático — para crear tags y Releases |

**Job `train` — pasos:**
1. Instala `model/requirements.txt`
2. Ejecuta `python model/train.py` → llama `ModelTrainer` + `ModelPromoter`
   - `ModelTrainer` registra en MLflow: 6 parámetros, 5 métricas y 4 etiquetas de trazabilidad (`git.commit_hash`, `git.ref`, `environment`, `pipeline.version`)
   - El modelo se registra con alias `Staging` en el Model Registry
   - `ModelPromoter` valida umbrales; si los supera, asigna alias `Production`
3. Parsea el output de `train.py` para extraer métricas e indicador `promoted`
4. Calcula el siguiente tag semver (`v{major}.{minor}.{patch+1}`) con `git tag --sort`
5. Solo si `promoted=true`: crea tag Git y GitHub Release con tabla de métricas
6. Sube artefactos locales a GitHub Actions (retención 90 días)

**Job `deploy` — encadenamiento a cd.yml:**
Se ejecuta tras `train` solo si `promoted=true`. Llama a `cd.yml` via `workflow_call` pasando el tag semver como input. Los releases creados con `GITHUB_TOKEN` no disparan el evento `on: release` en otros workflows, por lo que el encadenamiento es directo entre jobs.

**Falla si:** las métricas no superan los umbrales, MLflow no es alcanzable o el runner no está activo.

**Umbrales de promoción (`model/train.py`):**

| Métrica | Umbral mínimo |
|---|---|
| accuracy | 0.85 |
| f1 | 0.82 |
| roc_auc | 0.90 |

---

### `cd.yml` — Continuous Delivery

**Trigger:**
- `workflow_call` desde el job `deploy` de `ct.yml` (automático cuando `promoted=true`)
- `on: release` publicado (disparo directo si se crea un release manualmente)

**Runner:** `ubuntu-latest` (GitHub-hosted). No requiere runner local.

**job `build-push`:**
1. Login en GHCR con `GITHUB_TOKEN`
2. Extrae metadata de imagen — tag semver recibido como input + `latest`
3. Construye `services/api/Dockerfile` (stage `runtime`) con caché GHA
4. Push a `ghcr.io/{owner}/{repo}/api`

**job `smoke-test`** (depende de `build-push`):
1. Levanta stack efímero: `mlflow + otel-collector + api` con la imagen recién publicada
2. Espera readiness de la API (max 90 s, sondeo cada 3 s)
3. Valida `GET /health` → 200
4. Valida `POST /infer/` con muestra real del dataset → HTTP 200
5. Derriba el stack (`docker compose down -v`)

**Permisos:** `contents: read` + `packages: write`

**Falla si:** el build falla, la API no responde o la inferencia retorna código distinto de 200.

---

## Tags de imagen publicados en GHCR

| Tag | Ejemplo | Uso |
|---|---|---|
| Semver exacto | `v0.0.1` | Referencia inmutable para rollback |
| `latest` | — | Despliegue de producción por defecto |

```bash
# Listar versiones publicadas
gh api /user/packages/container/PipelineModeling%2Fapi/versions \
  --jq '.[0] | {version: .name, created_at}'
```

---

## Runner Local Automatizado

`manage.py start` y `manage.py stop` gestionan el ciclo de vida del runner de forma automática.

### Arranque automatico

`python manage.py start` ejecuta `_start_actions_runner()` tras levantar Docker Compose. La función:

1. Verifica que `C:\actions-runner\run.cmd` existe (no hace nada en hosts no Windows o sin runner instalado).
2. Comprueba si `Runner.Listener.exe` ya está en ejecución — si es así, lo omite sin abrir una segunda instancia.
3. Lanza `Start-Process pwsh -Verb RunAs` con una ventana PowerShell elevada nueva que ejecuta `.\run.cmd; pause`.
4. El usuario acepta el prompt UAC una sola vez por sesión de Windows.

El `pause` al final mantiene la ventana abierta tras la parada del runner, permitiendo leer el motivo del cierre.

### Parada automatica

`python manage.py stop` ejecuta `_stop_actions_runner()` antes de bajar Docker Compose. Usa `taskkill /F /IM Runner.Listener.exe` y `taskkill /F /IM Runner.Worker.exe`. Si `taskkill` falla por permisos (proceso elevado), emite una advertencia sin bloquear la bajada del stack.

### Comandos manuales (fallback)

Si la automatización falla o el runner ya estaba encendido manualmente:

```powershell
# Abrir PowerShell como Administrador
Set-Location C:\actions-runner
.\run.cmd
```

### Disparar entrenamiento continuo

```bash
gh workflow run ct.yml --repo VSXR/PipelineModeling --ref master
gh run watch --repo VSXR/PipelineModeling
```

---

## Self-hosted runner (requerido por ct.yml)

`ct.yml` ejecuta en el runner local (`runs-on: self-hosted`) porque MLflow está en `localhost:5000`. `ci.yml` y `cd.yml` usan runners GitHub-hosted (`ubuntu-latest`) y no requieren runner local.

### Instalación (ya realizada)

El runner está instalado en `C:\actions-runner` registrado como `pipeline-local` en el repositorio. Si necesitas reinstalarlo:

```powershell
# 1. Crear directorio y descargar
New-Item -ItemType Directory -Force -Path C:\actions-runner | Out-Null
Set-Location C:\actions-runner
Invoke-WebRequest -Uri https://github.com/actions/runner/releases/download/v2.334.0/actions-runner-win-x64-2.334.0.zip -OutFile actions-runner-win-x64-2.334.0.zip
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory("$PWD\actions-runner-win-x64-2.334.0.zip", "$PWD")

# 2. Configurar (el token caduca; generar uno nuevo en Settings → Actions → Runners → New runner)
.\config.cmd --url https://github.com/VSXR/PipelineModeling --token <TOKEN>
# Pulsar Enter en todas las preguntas; responder N a "run as service"
```

### Encender el runner

Abrir PowerShell como Administrador y ejecutar:

```powershell
Set-Location C:\actions-runner
.\run.cmd
```

El runner esta listo cuando aparece:

```
Connected to GitHub
Listening for Jobs
```

Verificar estado desde la terminal del proyecto:

```powershell
gh api repos/VSXR/PipelineModeling/actions/runners --jq ".runners[] | {name, status, busy}"
```

El campo `status` debe ser `online` y `busy` debe ser `false` cuando esta libre.

### Apagar el runner

Pulsar `Ctrl+C` en la ventana donde corre `.\run.cmd`. El runner pasa a estado `offline` en GitHub y los jobs quedan en cola hasta que vuelva a estar activo.

### Secuencia de uso habitual

```
1. Encender el stack + runner:  python manage.py start   (runner se lanza automáticamente con UAC)
2. Disparar CT:                 gh workflow run ct.yml --repo VSXR/PipelineModeling --ref master
3. Monitorizar:                 gh run watch --repo VSXR/PipelineModeling
4. Apagar el stack + runner:    python manage.py stop    (runner se termina antes de bajar Docker)
```

El runner debe estar activo durante toda la ejecucion de `ct.yml`. `cd.yml` corre en runners GitHub-hosted y no necesita que el runner local este activo.

---

## Configuración inicial en GitHub

### 1. Secretos de repositorio

**Settings → Secrets and variables → Actions:**

```
MLFLOW_TRACKING_URI        →  https://mlflow.example.com
MLFLOW_TRACKING_USERNAME   →  mlflow_user
MLFLOW_TRACKING_PASSWORD   →  ***
```

`GITHUB_TOKEN` es automático.

### 2. GitHub Packages (GHCR)

La imagen se publica en `ghcr.io/{owner}/{repo}/api`. Para repositorios privados, verificar que el token tiene scope `write:packages`.

### 3. Branch de producción

Los workflows apuntan a `master`. Si se renombra, actualizar las referencias en los tres YAML.

---

## Rollback de imagen

```bash
docker pull ghcr.io/{owner}/{repo}/api:sha-ef58985
# Actualizar la referencia de imagen en docker-compose.yml o el orquestador
```

Para rollback de modelo sin reconstruir imagen, usar hot-swap:

```bash
curl -X POST http://localhost:8000/version/switch \
  -H "Content-Type: application/json" \
  -d '{"model_ref": "2"}'
```

---

## Extender el pipeline de despliegue

Añadir un job `deploy-production` al final de `cd.yml`:

```yaml
deploy-production:
  name: Deploy to Production
  needs: [build-push, smoke-test]
  runs-on: ubuntu-latest
  environment: production        # requiere aprobación manual en GitHub
  steps:
    - name: Rollout
      run: |
        # Kubernetes:
        kubectl set image deployment/pipeline-api \
          api=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.image_digest }}
        # ECS:
        aws ecs update-service --cluster pipeline --service api --force-new-deployment
        # Cloud Run:
        gcloud run deploy pipeline-api \
          --image ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.image_digest }}
```

Activar el entorno `production` en **Settings → Environments** para requerir aprobación manual.
