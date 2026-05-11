# CI/CD — PipelineModeling

## Flujo completo

```
commit → master
    │
    ├─► ci.yml          (siempre)   — tests unitarios
    │
    └─► retrain.yml     (solo si cambia model/)
            │
            └─► deploy.yml  (solo si retrain crea tag v*)
```

Los tres workflows son independientes pero se encadenan por eventos: `ci.yml` corre en cada push; `retrain.yml` solo cuando cambia el código del modelo; `deploy.yml` solo cuando `retrain.yml` crea un tag `v*` en `master`.

---

## Workflows

### `ci.yml` — Tests en cada commit

**Trigger:** push a `master` o `develop`, PR hacia `master`.

**Qué hace:**
1. Instala `services/api/requirements.txt` + `tests/requirements.txt`
2. Ejecuta `pytest tests/ -k "not TestAPIEndpoints"` (tests unitarios, sin API levantada)

**Cuándo falla:** si algún test unitario rompe o hay errores de importación.

---

### `retrain.yml` — Reentrenamiento y publicación de métricas

**Trigger:**
- Push a `master` que modifique `model/train.py` o `model/requirements.txt`
- Cron semanal: lunes 02:00 UTC
- `workflow_dispatch` (manual, con parámetros `min_accuracy` y `min_f1`)

**Qué hace:**
1. Instala `model/requirements.txt`
2. Ejecuta `python model/train.py` → genera `model/weights/model.pkl` + `model/metrics.json`
3. Valida que `accuracy >= 0.80` y `f1 >= 0.80` (umbrales configurables)
4. Sube el artefacto del modelo a GitHub Actions (retención 90 días)
5. **Solo en `master`:** crea tag `v{YYYYMMDDHHMMSS}` y GitHub Release con tabla de métricas

**Secretos necesarios:**
| Secreto | Descripción | Obligatorio |
|---|---|---|
| `GITHUB_TOKEN` | Automático de GitHub Actions | Sí |
| `MLFLOW_TRACKING_URI` | URI del servidor MLflow de producción | No (usa `file:///tmp/mlruns` si no se configura) |

**Cuándo falla:** si las métricas no superan los umbrales configurados.

---

### `deploy.yml` — Build y push de imagen Docker

**Trigger:** creación de tag `v*` (generado automáticamente por `retrain.yml`).

**Qué hace:**
1. **build-push**: construye `services/api/Dockerfile` (stage `runtime`) y publica en GHCR con tags:
   - `v{semver}` — versión exacta del tag
   - `{major}.{minor}` — alias de minor
   - `sha-{short}` — referencia al commit
   - `latest` — solo en `master`
2. **smoke-test**: levanta `mlflow + otel-collector + api` con la imagen publicada, espera readiness y lanza una inferencia de prueba con sample real del dataset Breast Cancer
3. **deploy-production** *(comentado)*: punto de extensión para rollout a Kubernetes, ECS o Cloud Run

**Permisos necesarios:**
- `contents: read` + `packages: write` (para push a GHCR)
- El repositorio debe tener **GitHub Packages** habilitado

**Cuándo falla:** si el build falla, si la API no responde en 90 segundos, o si el endpoint `/infer/` no retorna HTTP 200.

---

## Configuración inicial en GitHub

### 1. Secretos de repositorio

Ir a **Settings → Secrets and variables → Actions** y añadir:

```
MLFLOW_TRACKING_URI   →  URI del servidor MLflow de producción
                          (omitir para usar almacenamiento local temporal en CI)
```

`GITHUB_TOKEN` es automático — no hace falta configurarlo.

### 2. GitHub Packages (GHCR)

La imagen se publica en `ghcr.io/{owner}/{repo}/api`. No requiere configuración adicional si el repositorio es público. Para repositorios privados, verificar que el token tiene scope `write:packages`.

### 3. Branch de producción

Los workflows están configurados para `master`. Si en algún momento se renombra el branch principal, actualizar las referencias `refs/heads/master` en los tres archivos de workflow.

---

## Imágenes Docker publicadas

| Tag | Cuándo se crea | Uso |
|---|---|---|
| `latest` | Cada tag en `master` | Despliegue de producción por defecto |
| `v20260511120000` | Cada retrain exitoso | Rollback a versión exacta |
| `sha-abc1234` | Cada build | Trazabilidad por commit |

Para hacer rollback manual a una versión anterior:

```bash
docker pull ghcr.io/{owner}/{repo}/api:v20260511120000
# Actualizar el tag de imagen en docker-compose.yml o en el orquestador
```

---

## Extender el pipeline de despliegue

El job `deploy-production` en `deploy.yml` está comentado. Para activarlo:

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
        aws ecs update-service --cluster pipeline --service api \
          --force-new-deployment

        # Cloud Run:
        gcloud run deploy pipeline-api \
          --image ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.image_digest }}
```

Añadir el entorno `production` en **Settings → Environments** para habilitar la aprobación manual antes del despliegue.
