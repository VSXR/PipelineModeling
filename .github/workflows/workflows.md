# GitHub Actions Workflows

Tres workflows cubren el ciclo de vida completo. Todos corren en runners `ubuntu-latest` de GitHub; no se requiere infraestructura propia.

---

## `ci.yml` — Integración Continua

**Trigger:** push a `master`, PR hacia `master`.

**Pasos:** lint con `ruff` + `pytest` unitarios (sin API levantada).

**Falla si:** el linter reporta errores o algún test unitario rompe.

---

## `ct.yml` — Entrenamiento Continuo

**Trigger:** push a `master`, `workflow_dispatch`.

**Secretos (todos opcionales):**

| Secret | Default | Descripción |
|---|---|---|
| `MLFLOW_TRACKING_URI` | `file:./mlruns` | Servidor MLflow externo; omitir para tracking local |
| `MLFLOW_TRACKING_USERNAME` | _(vacío)_ | Auth básica MLflow |
| `MLFLOW_TRACKING_PASSWORD` | _(vacío)_ | Auth básica MLflow |

**Jobs:**

- `ci` — gate que reutiliza `ci.yml`
- `train` — entrena con `ModelTrainer`, promueve con `ModelPromoter`, sube artefacto `model-{sha}`, calcula semver
- `deploy` — encadena `cd.yml` via `workflow_call` si `promoted=true`
- `release` — crea tag Git y GitHub Release con tabla de métricas

**Falla si:** las métricas no superan los umbrales de promoción (`accuracy ≥ 0.85`, `f1 ≥ 0.82`, `roc_auc ≥ 0.90`).

---

## `cd.yml` — Build y Publicación

**Trigger:** `workflow_call` desde `ct.yml`, o `on: release` publicado.

**Jobs:**

- `build-push` — construye `services/api/Dockerfile` (stage `runtime`), publica en `ghcr.io/{owner}/{repo}/api` con tags semver + `latest`
- `smoke-test` — descarga el artefacto `model-{sha}` del mismo run (o entrena bootstrap si no existe), levanta stack efímero `mlflow + otel-collector + api`, valida `/health` e `/infer/`, derriba el stack

**Permisos:** `contents: read` + `packages: write`.

**Portabilidad en forks:** activar `Settings → Actions → General → Workflow permissions → Read and write` para que `GITHUB_TOKEN` pueda hacer push a GHCR.
