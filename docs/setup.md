# Setup

## Prerrequisitos

| Herramienta | Versión mínima | Verificar |
|---|---|---|
| Python | 3.11 | `python --version` |
| Git | 2.x | `git --version` |
| Docker Desktop | 4.x | `docker compose version` |

> Docker ejecuta MLflow (registro de modelos), el OTel Collector (telemetría), Prometheus (scrape) y Grafana (dashboards). La API, el frontend y el seeder corren en local con `.venv`.

---

## Primera configuración

```powershell
.\pipeline.ps1 setup
```

Internamente:

1. Crea `.venv` con `python -m venv`
2. Instala todas las dependencias (`services/api`, `frontend`, `seeder`, `model`, `tests`)
3. Copia `.env.example → .env`
4. Entrena `model/weights/model.pkl` si no existe (breast_cancer, 30 features)

---

## Variables de entorno

Todas están en `.env` (generado desde `.env.example`).

| Variable | Por defecto | Descripción |
|---|---|---|
| `MODEL_PATH` | ruta local al `.pkl` | Ruta del artefacto del modelo para carga en startup |
| `MLFLOW_TRACKING_URI` | `http://mlflow:5000` | URL del servidor MLflow (Model Registry) |
| `MLFLOW_MODEL_NAME` | `pipeline-model` | Nombre del modelo en el registry |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | _(vacío = no-op)_ | Endpoint gRPC del OTel Collector |
| `OTEL_SERVICE_NAME` | `pipeline-api` | Nombre del servicio en trazas y métricas |
| `GRAFANA_URL` | `http://localhost:3000` | URL usada por el frontend para acceder a Grafana |
| `PROMETHEUS_URL` | `http://localhost:9090` | URL usada por el frontend para acceder a Prometheus |
| `REQUESTS_PER_SECOND` | `20` | Tasa de inferencia del seeder |
| `INFERENCE_CONCURRENCY` | `10` | Peticiones HTTP en vuelo simultáneas |
| `TRAINING_INTERVAL_S` | `30` | Segundos entre batches de entrenamiento |
| `TRAINING_BATCH_SIZE` | `50` | Muestras por batch |
| `DRIFT_ONSET_AFTER_S` | `120` | Segundos hasta activar la deriva |
| `DRIFT_MAGNITUDE` | `2.0` | Magnitud del desplazamiento gaussiano |

> En modo local (`.venv`), omitir `OTEL_EXPORTER_OTLP_ENDPOINT` hace que el SDK opere en modo no-op: las métricas se contabilizan internamente pero no se exportan.

---

## Instalación manual (alternativa)

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

---

## Dependencias principales

| Paquete | Versión | Uso |
|---|---|---|
| `fastapi` | 0.111.0 | Framework de la API REST |
| `uvicorn[standard]` | 0.29.0 | Servidor ASGI |
| `scikit-learn` | 1.4.2 | SGDClassifier, train_test_split, métricas |
| `opentelemetry-api` | 1.24.0 | Contratos de instrumentación (sin vendor) |
| `opentelemetry-sdk` | 1.24.0 | MeterProvider, PeriodicExportingMetricReader |
| `opentelemetry-exporter-otlp-proto-grpc` | 1.24.0 | Exportación OTLP gRPC al Collector |
| `opentelemetry-instrumentation-fastapi` | 0.45b0 | Trazas automáticas en FastAPI |
| `mlflow-skinny` | 2.12.2 | Cliente ligero del Model Registry (solo API) |
| `mlflow` | 2.12.2 | Cliente completo para entrenamiento y registro |
| `streamlit` | 1.35.0 | Frontend interactivo |
| `httpx` | 0.27.0 | Cliente HTTP async (wrapper + tests) |

---

## Iniciar el stack completo
 + Prometheus + Grafana
docker compose up mlflow otel-collector prometheus grafana
# Docker: MLflow + OTel Collector
docker compose up mlflow otel-collector -d

# Local: API + Frontend + Seeder
.\pipeline.ps1 start
```

O todo en Docker:

```powershell
docker compose up -d
```

---

## Verificar el stack

| Comprobación | Comando |
|---|---|
| API health | `Invoke-RestMethod http://localhost:8000/health` |
| MLflow UI | Abrir http://localhost:5000 en el navegador |
| Prometheus UI | Abrir http://localhost:9090 en el navegador |
| Grafana UI | Abrir http://localhost:3000 en el navegador |
| OTel Collector zPages | Abrir http://localhost:55679 en el navegador |
| Logs del Collector | `docker compose logs otel-collector --follow` |

---

## Permisos de ejecución de scripts en PowerShell

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

---

## Variables de entorno para CI/CD (GitHub Actions)

Definir en *Settings → Secrets and variables → Actions* del repositorio:

| Secret | Descripción |
|---|---|
| `MLFLOW_TRACKING_URI` | URL del servidor MLflow de producción (omitir para usar `file:///tmp/mlruns`) |

El workflow `deploy.yml` usa `GITHUB_TOKEN` (automático) para push a GHCR.
