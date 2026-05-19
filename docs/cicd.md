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

**Runner:** `ubuntu-latest` (GitHub-hosted). No requiere runner local ni infraestructura propia.

**Secretos — todos opcionales:**

| Secreto | Por defecto si ausente | Descripción |
|---|---|---|
| `MLFLOW_TRACKING_URI` | `file:./mlruns` | URI del servidor MLflow. Si no se configura, usa tracking local en el runner efímero |
| `MLFLOW_TRACKING_USERNAME` | _(vacío)_ | Usuario de autenticación básica MLflow |
| `MLFLOW_TRACKING_PASSWORD` | _(vacío)_ | Contraseña de autenticación básica MLflow |
| `GITHUB_TOKEN` | Automático | Para crear tags y Releases |

Con los defaults, el pipeline funciona en cualquier fork sin configurar ningún secreto.

**Job `train` — pasos:**
1. Instala `model/requirements.txt`
2. Ejecuta `python model/train.py` → llama `ModelTrainer` + `ModelPromoter`
   - `ModelTrainer` registra en MLflow: 6 parámetros, 5 métricas y 4 etiquetas de trazabilidad (`git.commit_hash`, `git.ref`, `environment`, `pipeline.version`)
   - El modelo se registra con alias `Staging` en el Model Registry
   - `ModelPromoter` valida umbrales; si los supera, asigna alias `Production`
3. Parsea el output de `train.py` para extraer métricas e indicador `promoted`
4. Calcula el siguiente tag semver (`v{major}.{minor}.{patch+1}`) con `git tag --sort`
5. Solo si `promoted=true`: crea tag Git y GitHub Release con tabla de métricas
6. Sube artefactos locales a GitHub Actions (retención 90 días): `model/weights/model.pkl` + `model/metrics.json`

**Job `deploy` — encadenamiento a cd.yml:**
Se ejecuta tras `train` solo si `promoted=true`. Llama a `cd.yml` via `workflow_call` pasando el tag semver como input. Los releases creados con `GITHUB_TOKEN` no disparan el evento `on: release` en otros workflows, por lo que el encadenamiento es directo entre jobs.

**Falla si:** las métricas no superan los umbrales o el entrenamiento lanza una excepción.

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
1. Descarga el artefacto `model-{sha}` subido por `ct.yml` (si existe en el mismo run)
2. Si el artefacto no está disponible (trigger directo via `on: release`), entrena un modelo bootstrap con `file:./mlruns`
3. Levanta stack efímero: `mlflow + otel-collector + api` con la imagen recién publicada
4. Espera readiness de la API (max 180 s, sondeo cada 5 s)
5. Valida `GET /health` → 200
6. Valida `POST /infer/` con muestra real del dataset → HTTP 200
7. Derriba el stack (`docker compose down -v`)

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

## Runner local (solo desarrollo en Windows)

Los tres workflows (`ci.yml`, `ct.yml`, `cd.yml`) usan runners `ubuntu-latest` de GitHub. El runner local de Windows es opcional y sirve únicamente para development local avanzado.

`manage.py start` lanza el runner automáticamente si detecta `%ACTIONS_RUNNER_DIR%\run.cmd` (por defecto `C:\actions-runner`). En Linux/macOS la llamada es silenciosa.

Para sobreescribir la ruta del runner:

```powershell
$env:ACTIONS_RUNNER_DIR = "D:\mis-runners\pipeline"
python manage.py start
```

### Disparar entrenamiento continuo

```bash
gh workflow run ct.yml --repo VSXR/PipelineModeling --ref master
gh run watch --repo VSXR/PipelineModeling
```

---

## Configuración inicial en GitHub

### 1. Secretos de repositorio (opcionales)

Sin secretos configurados el pipeline funciona completo con tracking local y la imagen se publica en el GHCR del propio repositorio.

**Settings → Secrets and variables → Actions** (solo si se quiere usar un servidor MLflow externo):

```
MLFLOW_TRACKING_URI        →  https://mlflow.example.com   (default: file:./mlruns)
MLFLOW_TRACKING_USERNAME   →  mlflow_user                  (default: vacío)
MLFLOW_TRACKING_PASSWORD   →  ***                          (default: vacío)
```

`GITHUB_TOKEN` es automático.

### 2. GitHub Packages (GHCR)

La imagen se publica en `ghcr.io/{owner}/{repo}/api` usando `${{ github.repository }}`, por lo que en un fork se publica automáticamente en el GHCR del fork.

Para forks: activar **Settings → Actions → General → Workflow permissions → Read and write** para que `GITHUB_TOKEN` pueda hacer push a GHCR.

### 3. Branch de producción

Los workflows apuntan a `master`. Si se renombra, actualizar las referencias en los tres YAML.

### 4. Override de endpoints en docker-compose

Para apuntar a servicios externos en local, basta con editar `.env`:

```dotenv
MLFLOW_TRACKING_URI=https://mi-mlflow.ejemplo.com
OTEL_EXPORTER_OTLP_ENDPOINT=https://mi-otel.ejemplo.com:4317
```

`docker-compose.yml` lee estas variables con defaults incorporados; no requiere editar el YAML.

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
