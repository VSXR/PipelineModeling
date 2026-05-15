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
| [test_inference.py](../tests/test_inference.py) | 11 | Predicción binaria 30 features, probabilidades suman 1, `request_id`, 4 entradas inválidas (422), 20 req concurrentes |
| [test_training.py](../tests/test_training.py) | 12 | `partial_fit`, `samples_trained`, versión actualizada, 5 entradas inválidas (422), drift score EMA |
| [test_versioning.py](../tests/test_versioning.py) | 7 | `/version/current`, consistencia con `/health`, ref inexistente (500), ref vacío (422) |
| [test_metrics.py](../tests/test_metrics.py) | 7 | 8 métricas presentes, `model_loaded=1.0`, contadores incrementan, histograma de latencia |
| [test_flow.py](../tests/test_flow.py) | 8 | Golden path (health→infer→train→infer→drift→metrics→version), `request_id` propagation |
| [test_observability_stack.py](../tests/test_observability_stack.py) | 17 | Collector → Prometheus → Grafana — ver sección Observabilidad |
| [test_otel_mlflow_migration.py](../tests/test_otel_mlflow_migration.py) | — | Migración OTel + MLflow (legacy) |

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
OTEL_COLLECTOR_URL=http://localhost:9464
PROMETHEUS_URL=http://localhost:9090
GRAFANA_URL=http://localhost:3000
GF_ADMIN_PASSWORD=admin
```

### Clases de test

**TestCollectorMetricsExposition** — OTel Collector expone métricas Prometheus en `:9464`:
- `test_collector_prometheus_endpoint_responds`
- `test_collector_metrics_format_valid`

**TestPrometheusIntegration** — Prometheus scrapea y almacena métricas:
- `test_prometheus_is_healthy`
- `test_prometheus_has_scrape_targets`
- `test_prometheus_scrapes_otel_collector`
- `test_prometheus_has_pipeline_metrics`
- `test_prometheus_stores_inference_latency`

**TestGrafanaIntegration** — Grafana configurada y provisionada:
- `test_grafana_is_healthy`
- `test_grafana_has_prometheus_datasource`
- `test_prometheus_datasource_is_accessible`
- `test_grafana_has_dashboard_provisioned`
- `test_dashboard_panels_exist`
- `test_dashboard_panel_targets_prometheus`

**TestMetricsFlowThroughStack** — métricas se propagan por el stack:
- `test_inference_metrics_reach_prometheus`
- `test_inference_latency_histogram_exists`
- `test_model_loaded_gauge_accessible_from_grafana`

**TestStackIntegrationEnd2End**:
- `test_metrics_flow_from_api_to_grafana` — flujo completo API → Collector → Prometheus → Grafana

### Ejecución selectiva

```bash
pytest tests/test_observability_stack.py -v
pytest tests/test_observability_stack.py::TestGrafanaIntegration -v
pytest tests/test_observability_stack.py::TestPrometheusIntegration::test_prometheus_scrapes_otel_collector -v
```

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
| `test_collector_prometheus_endpoint_responds` falla | Collector no alcanzable | `docker compose up -d otel-collector` |
| `test_prometheus_scrapes_otel_collector` falla (target DOWN) | Red Docker mal configurada | `docker logs pipeline_otel_collector` |
| `test_grafana_has_prometheus_datasource` falla | Grafana no ha leído el provisioning | `docker compose restart grafana` |
| `test_grafana_has_dashboard_provisioned` falla | JSON de dashboard no encontrado | `docker exec pipeline_grafana ls /etc/grafana/provisioning/dashboards/` |

### Debugging rápido

```bash
# Verificar métricas del Collector
curl http://localhost:9464/metrics | head -20

# Consultar Prometheus
curl "http://localhost:9090/api/v1/query?query=up"

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
