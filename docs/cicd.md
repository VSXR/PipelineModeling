# CI/CD — PipelineModeling

## Flujo completo

```
commit → master
    │
    ├─► ci.yml          (siempre)              — lint + tests unitarios
    │
    └─► ct.yml          (solo si cambia model/) — entrenamiento continuo
            │
            └─► cd.yml  (solo si CT crea Release) — build + push GHCR
```

Los tres workflows se encadenan por eventos: `ci.yml` en cada push; `ct.yml` solo cuando cambia `model/`; `cd.yml` solo cuando `ct.yml` publica un GitHub Release.

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

**Secretos necesarios:**

| Secreto | Descripción |
|---|---|
| `MLFLOW_TRACKING_URI` | URI del servidor MLflow remoto |
| `MLFLOW_TRACKING_USERNAME` | Usuario de autenticación básica MLflow |
| `MLFLOW_TRACKING_PASSWORD` | Contraseña de autenticación básica MLflow |
| `GITHUB_TOKEN` | Automático — para crear tags y Releases |

**Pasos:**
1. Instala `model/requirements.txt`
2. Ejecuta `python model/train.py` → llama `ModelTrainer` + `ModelPromoter`
   - `ModelTrainer` registra en MLflow: 6 parámetros, 5 métricas y 4 etiquetas de trazabilidad (`git.commit_hash`, `git.ref`, `environment`, `pipeline.version`)
   - El modelo se registra con alias `Staging` en el Model Registry
   - `ModelPromoter` valida umbrales; si los supera, asigna alias `Production`
3. Parsea el output de `train.py` para extraer métricas e indicador `promoted`
4. Calcula el siguiente tag semver (`v{major}.{minor}.{patch+1}`)
5. **Solo si `promoted=true`:** crea tag Git y GitHub Release con tabla de métricas
6. Sube artefactos locales a GitHub Actions (retención 90 días)

**Falla si:** las métricas no superan los umbrales o MLflow no es alcanzable.

**Umbrales de promoción (`model/train.py`):**

| Métrica | Umbral mínimo |
|---|---|
| accuracy | 0.85 |
| f1 | 0.82 |
| roc_auc | 0.90 |

---

### `cd.yml` — Continuous Delivery

**Trigger:** publicación de un GitHub Release (generado automáticamente por `ct.yml`).

**Pasos:**

**job `build-push`:**
1. Login en GHCR con `GITHUB_TOKEN`
2. Extrae metadata de imagen — tags semver + SHA + `latest`
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
| Semver exacto | `v1.0.4` | Referencia inmutable para rollback |
| Major.minor | `1.0` | Alias de rolling minor |
| SHA corto | `sha-ef58985` | Trazabilidad exacta al commit |
| `latest` | — | Despliegue de producción por defecto |

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
