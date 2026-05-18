# Testing

## Ejecutar los tests

```powershell
# Con el CLI (recomendado)
python manage.py test

# Solo tests unitarios (sin API)
python manage.py test --unit

# Solo tests de integración (requiere API corriendo)
python manage.py test --integration

# Directamente con pytest
.venv\Scripts\pytest tests/ -v --tb=short

# Contra una URL diferente
$env:API_URL = "http://staging:8000"
.venv\Scripts\pytest tests/
```

Los tests se **auto-omiten** (`pytest.skip`) si la API no está disponible, por lo que no fallan en entornos sin servidor.

---

## Suite completa

| Archivo | Tests | Qué cubre |
|---|---|---|
| [test_health.py](../tests/test_health.py) | 4 | `/health`: 200, `status=ok`, `model_loaded=True`, version string |
| [test_inference.py](../tests/test_inference.py) | 10 | Predicción binaria 30 features, probabilidades suman 1, `request_id`, 2 entradas inválidas (422), 20 req concurrentes |
| [test_training.py](../tests/test_training.py) | 8 | `partial_fit`, `samples_trained`, versión actualizada tras entrenamiento, 2 entradas inválidas (422) |
| [test_versioning.py](../tests/test_versioning.py) | 9 | `/version/current`, consistencia con `/health`, ref inexistente (500), ref vacío (422), `register` + `switch` a versión registrada |
| [test_flow.py](../tests/test_flow.py) | 3 | Golden path (health→infer→train→version), `request_id` propagation, múltiples rondas de entrenamiento |
| [test_observability.py](../tests/test_observability.py) | 16 | Infraestructura (HA-07..HA-12), métricas Prometheus de referencia (PA-01..PA-05), métricas operativas (PA-06..PA-10) |
| [test_otel_mlflow_migration.py](../tests/test_otel_mlflow_migration.py) | 19 | `PipelineMetrics` no-op, `ModelManager` startup, `VersionSwitch`, `DriftTracker` OTel, configuración limpia |

---

## Fixtures y configuración

`tests/conftest.py` define un `httpx.Client` de alcance sesión:

```python
@pytest.fixture(scope="session")
def client(api_url: str) -> httpx.Client:
    with httpx.Client(base_url=api_url, timeout=15.0) as c:
        try:
            c.get("/health").raise_for_status()
        except Exception as exc:
            pytest.skip(f"API not available at {api_url} — {exc}")
        yield c
```

Un único cliente HTTP se comparte entre todos los tests. El estado del modelo se acumula a lo largo de la sesión — `test_flow.py` verifica que el estado es coherente entre operaciones consecutivas.

### Vector de features de referencia (`FEATURES_30`)

Muestra #0 del dataset breast cancer (maligno, clase 0):

```python
FEATURES_30 = [
    17.99, 10.38, 122.80, 1001.0, 0.1184, 0.2776, 0.3001, 0.1471, 0.2419, 0.0787,
     1.095,  0.905,   8.589,  153.4, 0.0064, 0.0490, 0.0537, 0.0159, 0.0300, 0.0062,
    25.38,  17.33,  184.60, 2019.0, 0.1622, 0.6656, 0.7119, 0.2654, 0.4601, 0.1189,
]
```

### `pytest.ini`

```ini
[pytest]
testpaths = tests
addopts   = -v --tb=short
```

---

## Tests de observabilidad

Requieren el stack Docker completo corriendo (`python manage.py start`).

Variables de entorno (con defaults):

```bash
API_URL=http://localhost:8000
PROMETHEUS_URL=http://localhost:9090
GRAFANA_URL=http://localhost:3000
GF_ADMIN_PASSWORD=admin
```

### Clases de test (`test_observability.py`)

**TestInfrastructureHealth** — salud de cada servicio del stack (HA-07..HA-12):
- `test_grafana_health`
- `test_prometheus_ready`
- `test_otel_prom_exporter_reachable_and_has_inference_metric`
- `test_otel_health_extension` — requiere puerto 13133 mapeado en docker-compose
- `test_mlflow_health`
- `test_frontend_health`

**TestPrometheusBaselineMetrics** — estado base con seeder activo (PA-01..PA-05):
- `test_otel_collector_target_up`
- `test_model_loaded_gauge_is_one`
- `test_inference_requests_counter_positive`
- `test_training_samples_counter_positive`
- `test_drift_score_series_count_equals_feature_count`

**TestPrometheusOperationalMetrics** — umbrales de rendimiento (PA-06..PA-10):
- `test_inference_latency_p99_under_500ms`
- `test_error_rate_under_1pct` — ver advertencia post-chaos
- `test_drift_score_elevated_after_simulation` — requiere `DRIFT_VALIDATED=1`
- `test_version_switches_ok_recorded`
- `test_model_load_p99_under_10s`

### Variable de entorno para tests con condición temporal

```bash
# Activar la aserción de drift elevado (PA-08)
# Ejecutar inmediatamente después de: python manage.py simulate --scenario drift
# No usar junto con --scenario all (el tráfico normal entre escenarios degrada la señal EMA)
DRIFT_VALIDATED=1 python manage.py test
```

### Ejecución selectiva

```bash
pytest tests/test_observability.py -v
pytest tests/test_observability.py::TestInfrastructureHealth -v
pytest tests/test_observability.py::TestPrometheusOperationalMetrics::test_inference_latency_p99_under_500ms -v
```

### Advertencias sobre falsos positivos temporales

**PA-07 post-chaos (error rate):** El escenario `chaos` inyecta un 20% de errores durante 240 s. Al finalizar, el reset es efectivo en la API, pero Prometheus mantiene los contadores dentro de la ventana `rate([5m])`. El test `test_error_rate_under_1pct` fallará si se ejecuta dentro de los 5 minutos siguientes al escenario chaos. Esperar ese margen o ejecutar la suite antes de lanzar las simulaciones.

**PA-08 EMA decay (drift score):** El `DriftTracker` usa EMA con α = 0.05. Con el seeder a 20 req/s, el drift score decae a valores próximos a 0 en 3–5 minutos de tráfico normal. Para que `test_drift_score_elevated_after_simulation` pase, ejecutar la suite con `DRIFT_VALIDATED=1` dentro de los primeros 60 s tras completar `--scenario drift` y con el seeder detenido.

**PA-10 ventana de exportación OTel:** El SDK OTel exporta métricas cada 15 s. Tests que validan métricas recientes (como load duration tras un version switch) pueden observar datos ausentes si se ejecutan dentro de esa ventana. El test `test_model_load_p99_under_10s` se omite automáticamente cuando no hay datos disponibles.

### Arquitectura del stack de observabilidad

```
┌─────────────┐
│   FastAPI   │
│  :8000      │
└──────┬──────┘
       │ OTLP gRPC → otel-collector:4317
       ▼
┌──────────────────┐
│  OTel Collector  │
│  :9464 (Prom)    │
│  :4317 (OTLP)    │
│  :55679 (zPages) │
└──────┬───────────┘
       │ Prometheus scrape → otel-collector:9464/metrics
       ▼
┌─────────────────┐
│  Prometheus     │
│  :9090          │
│  scrape: 15s    │
└────────┬────────┘
         │ PromQL → prometheus:9090/api/v1/query
         ▼
┌──────────────────┐
│  Grafana         │
│  :3000           │
│  pipeline-       │
│  overview        │
└──────────────────┘
```

### Resolución de fallos frecuentes

| Error | Causa | Solución |
|---|---|---|
| `test_otel_prom_exporter_reachable_and_has_inference_metric` falla | Collector no alcanzable o sin tráfico previo | `docker compose up -d otel-collector`; enviar al menos una petición a `/infer/` |
| `test_otel_health_extension` falla o es skipped | Puerto 13133 no mapeado al host | Verificar que `docker-compose.yml` incluye `"13133:13133"` en los ports del otel-collector |
| `test_otel_collector_target_up` falla (target DOWN) | Red Docker mal configurada | `docker compose logs pipeline_otel_collector` |
| `test_grafana_health` falla | Grafana depende de Prometheus healthy | `docker compose ps`; si Prometheus no arrancó, verificar que `depends_on` usa `condition: service_healthy` |
| `test_drift_score_series_count_equals_feature_count` falla | Seeder aún no generó 50 inferencias | Esperar 30 s tras arranque del stack y reintentar |

### Debugging rápido

```bash
# Verificar métricas del Collector
curl http://localhost:9464/metrics | head -20

# Consultar Prometheus (PromQL directa)
curl "http://localhost:9090/api/v1/query?query=up"
curl "http://localhost:9090/api/v1/query?query=pipeline_model_loaded"

# Healthcheck del OTel Collector
curl http://localhost:13133/

# Listar datasources de Grafana
curl -u admin:admin http://localhost:3000/api/datasources
```

---

## Añadir nuevos tests

1. Crea `tests/test_<funcionalidad>.py`
2. Usa el fixture `client: httpx.Client` para las llamadas HTTP
3. Para tests parametrizados: `@pytest.mark.parametrize`

```python
from conftest import FEATURES_30

def test_infer_returns_binary(client):
    body = client.post("/infer/", json={"features": FEATURES_30}).json()
    assert body["prediction"] in (0, 1)
```

---

## Instalar dependencias de test

```powershell
.venv\Scripts\pip install -r tests/requirements.txt
```

Dependencias: `pytest==8.2.0`, `httpx==0.27.0`.
