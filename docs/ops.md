# Operaciones

## Prerrequisitos

| Herramienta | Versión mínima | Verificar |
|---|---|---|
| Python | 3.11 | `python --version` |
| Docker Desktop | 4.x | `docker compose version` |
| GitHub CLI | 2.x | `gh --version` |

Docker ejecuta MLflow, OTel Collector, Prometheus y Grafana. La API, frontend y seeder corren en `.venv`.

## Setup inicial

```powershell
python manage.py setup
# Crea .venv, instala deps, copia .env.example→.env, entrena model/weights/model.pkl
```

**Manual:**
```powershell
python -m venv .venv
.venv\Scripts\pip install `
  -r services/api/requirements.txt `
  -r services/frontend/requirements.txt `
  -r services/seeder/requirements.txt `
  -r model/requirements.txt `
  -r tests/requirements.txt
Copy-Item .env.example .env
.venv\Scripts\python model/train.py
```

**PowerShell execution policy:**
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

---

## Variables de entorno (`.env`)

| Variable | Por defecto | Descripción |
|---|---|---|
| `MODEL_PATH` | ruta local al `.pkl` | Ruta del artefacto |
| `MLFLOW_TRACKING_URI` | `http://mlflow:5000` | URL servidor MLflow |
| `MLFLOW_MODEL_NAME` | `pipeline-model` | Nombre en el registry |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | _(vacío = no-op)_ | Endpoint gRPC del Collector |
| `OTEL_SERVICE_NAME` | `pipeline-api` | Nombre del servicio en trazas |
| `GRAFANA_URL` | `http://localhost:3000` | URL Grafana para el frontend |
| `PROMETHEUS_URL` | `http://localhost:9090` | URL Prometheus para el frontend |
| `REQUESTS_PER_SECOND` | `20` | Tasa de inferencia del seeder |
| `TRAINING_INTERVAL_S` | `30` | Segundos entre batches de entrenamiento |
| `TRAINING_BATCH_SIZE` | `50` | Muestras por batch |
| `DRIFT_ONSET_AFTER_S` | `120` | Segundos hasta activar deriva |
| `DRIFT_MAGNITUDE` | `2.0` | Magnitud del desplazamiento gaussiano |

**CI/CD GitHub Actions** — todos opcionales; sin ellos el pipeline usa `file:./mlruns`:

| Secret | Por defecto |
|---|---|
| `MLFLOW_TRACKING_URI` | `file:./mlruns` |
| `MLFLOW_TRACKING_USERNAME` | _(vacío)_ |
| `MLFLOW_TRACKING_PASSWORD` | _(vacío)_ |

`GITHUB_TOKEN` es automático. Para forks: **Settings → Actions → General → Workflow permissions → Read and write**.

---

## Stack

```powershell
python manage.py start          # .venv + Docker (desarrollo)
docker compose up --build       # solo Docker (demo/integración)
docker compose down -v          # reset completo con borrado de volúmenes
```

| Aspecto | `manage.py start` | `docker compose up` |
|---|---|---|
| API / Frontend / Seeder | `.venv` con `--reload` | Contenedores |
| MLflow / OTel / Prometheus / Grafana | Docker | Docker |
| Recarga automática | Sí | No |
| Ideal para | Desarrollo iterativo | Demo, integración |

**Verificar stack:**
```powershell
Invoke-RestMethod http://localhost:8000/health
```

---

## Dependencias principales

| Paquete | Versión | Uso |
|---|---|---|
| `fastapi` | 0.111.0 | API REST |
| `uvicorn[standard]` | 0.29.0 | Servidor ASGI |
| `scikit-learn` | 1.4.2 | SGDClassifier |
| `opentelemetry-sdk` | 1.24.0 | MeterProvider, exportación OTLP |
| `opentelemetry-exporter-otlp-proto-grpc` | 1.24.0 | Exportación OTLP gRPC |
| `mlflow-skinny` | 2.12.2 | Cliente Model Registry |
| `streamlit` | 1.35.0 | Frontend |
| `httpx` | 0.27.0 | Cliente HTTP async |

---

## Desarrollo iterativo

```bash
python manage.py start
# editar services/api/ o services/frontend/  (uvicorn --reload activo)
python manage.py test --integration
python manage.py stop
```

**Añadir endpoint:**
1. Router en `services/api/routers/`
2. Schema en `services/api/schemas/`
3. Registrar en `services/api/main.py`
4. Tests en `tests/test_<nombre>.py`
5. Métricas nuevas en `services/api/core/metrics.py`

**Añadir modelo (implementar BasePredictor):**
```python
class XGBoostPredictor(BasePredictor):
    def predict(self, X): ...
    def partial_fit(self, X, y): ...
    def save(self, path): ...
    @classmethod
    def load(cls, path): ...
    @classmethod
    def create_default(cls): ...
```
Cambiar `self._predictor = SKLearnPredictor.load(path)` en `model_manager.py`.

**Añadir endpoint al frontend:**
wrapper en `client.py` → coroutine en `network.py` → controlador en `controller.py` → campo en `domain.py` → render en `runtime.py`.

**Reconstruir un servicio Docker específico:**
```powershell
docker compose up --build api --no-deps
```

---

## Logs y limpieza

```powershell
docker compose logs -f api seeder
docker compose logs -f --tail=100 api
docker compose logs otel-collector --follow
```

```powershell
python manage.py stop
docker compose down -v
Remove-Item -Recurse .venv
```

---

## Problemas frecuentes

| Síntoma | Solución |
|---|---|
| API no disponible en tests | `python manage.py start` antes de `test --integration` |
| Playwright no encuentra navegador | `playwright install chromium` |
| Runner UAC rechazado | Ejecutar como Administrador: `cd C:\actions-runner; .\run.cmd` |
| Puerto 8000 ocupado | `Get-NetTCPConnection -LocalPort 8000 \| ForEach-Object { Get-Process -Id $_.OwningProcess }` |
| `docker compose build` falla (apt-get cache obsoleta) | `docker compose build --no-cache api` |
| Grafana "No data" en version switch | Ejecutar al menos un `POST /version/switch` manual |
| Frontend no conecta API | Verificar `API_URL=http://localhost:8000`; en Docker usar `http://api:8000` |
| Tests E2E FE-04/FE-07 rompen tras actualizar streamlit | `pytest tests/test_frontend.py -m fragile` y ajustar selectores DOM |
