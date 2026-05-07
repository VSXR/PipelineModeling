# Monitorización

## Flujo de métricas

```mermaid
graph LR
    API["API :8000\n/metrics"] -->|scrape cada 15s| PROM["Prometheus\n:9090"]
    PROM -->|PromQL| GRAF["Grafana\n:3000\ndashboards"]
    PROM -->|evalúa reglas| ALERT["alerts.yml\nModelNotLoaded\nHighErrorRate\nHighLatency\nDataDrift"]
```

## Acceso

| URL | Servicio |
|---|---|
| http://localhost:9090 | Prometheus — explorador de métricas y alertas |
| http://localhost:3000 | Grafana — dashboards (usuario: `admin`, contraseña: ver `.env`) |

---

## Métricas Prometheus

Todas las métricas tienen el prefijo `pipeline_`.

| Métrica | Tipo | Etiquetas | Descripción |
|---|---|---|---|
| `pipeline_model_loaded` | Gauge | — | `1` cuando el modelo está cargado, `0` durante hot-swap o fallo |
| `pipeline_inference_requests_total` | Counter | `status={ok,error}` | Total de peticiones de inferencia |
| `pipeline_inference_latency_seconds` | Histogram | — | Latencia end-to-end del endpoint `/infer/` |
| `pipeline_training_requests_total` | Counter | `status={ok,error}` | Total de peticiones de entrenamiento |
| `pipeline_training_samples_total` | Counter | — | Total de muestras procesadas con `partial_fit` |
| `pipeline_data_drift_score` | Gauge | `feature={nombre}` | Score de drift por feature (EMA, rango 0–∞) |
| `pipeline_version_switches_total` | Counter | `status={ok,error}` | Total de cambios de versión DVC |
| `pipeline_model_load_duration_seconds` | Histogram | — | Tiempo de DVC pull + joblib reload en cada version switch |

### Labels de drift (`feature`)

Las 30 features del dataset breast cancer se usan como labels de Prometheus:

```
radius_mean    texture_mean    perimeter_mean  area_mean
smoothness_mean  compactness_mean  concavity_mean  concpts_mean
symmetry_mean  fracdim_mean
radius_se      texture_se      perimeter_se    area_se
smoothness_se  compactness_se  concavity_se    concpts_se
symmetry_se    fracdim_se
radius_worst   texture_worst   perimeter_worst area_worst
smoothness_worst  compactness_worst  concavity_worst  concpts_worst
symmetry_worst fracdim_worst
```

### Consultas útiles en Prometheus

```promql
# Tasa de inferencias por segundo (últimos 5 min)
rate(pipeline_inference_requests_total{status="ok"}[5m])

# Tasa de errores (últimos 5 min)
rate(pipeline_inference_requests_total{status="error"}[5m])

# Latencia p99 de inferencia
histogram_quantile(0.99, rate(pipeline_inference_latency_seconds_bucket[5m]))

# Muestras de entrenamiento acumuladas
pipeline_training_samples_total

# Features con drift alto (> 0.5)
pipeline_data_drift_score > 0.5

# Features con mayor drift (ordena top 5)
topk(5, pipeline_data_drift_score)

# Duración del último version switch (percentil 95)
histogram_quantile(0.95, rate(pipeline_model_load_duration_seconds_bucket[1h]))

# Total de version switches exitosos
pipeline_version_switches_total{status="ok"}
```

---

## Dashboard Grafana

El dashboard **PipelineModeling** se provisiona automáticamente al arrancar Grafana.

| Panel | Métrica / Consulta |
|---|---|
| Inference RPS | `rate(pipeline_inference_requests_total[1m])` |
| Error rate | Porcentaje de `status="error"` sobre el total |
| Latencia p50 / p95 / p99 | `histogram_quantile` sobre `inference_latency_seconds` |
| Training samples (acumulado) | `pipeline_training_samples_total` |
| Model loaded | `pipeline_model_loaded` |
| Drift score por feature | `pipeline_data_drift_score{feature=~".*"}` |
| Version switches | `pipeline_version_switches_total` |
| Model load duration (DVC pull) | `pipeline_model_load_duration_seconds` |

> Si los paneles muestran "No data" al arrancar, espera 15–20 s para el primer scrape de Prometheus.  
> Verifica que http://localhost:9090/targets muestra `pipeline_api` en estado **UP**.  
> Los paneles "Version Switches" y "Model Load Duration" necesitan al menos una llamada a `POST /version/switch` para mostrar datos.

---

## Alertas

Definidas en `monitoring/prometheus/alerts.yml`:

| Alerta | Condición | Durante | Severidad |
|---|---|---|---|
| `ModelNotLoaded` | `pipeline_model_loaded == 0` | 1 min | critical |
| `HighInferenceErrorRate` | tasa de errores > 5 % | 5 min | warning |
| `HighInferenceLatencyP99` | p99 > 500 ms | 3 min | warning |
| `DataDriftDetected` | `pipeline_data_drift_score > 0.5` | 5 min | warning |

Ver alertas activas en http://localhost:9090/alerts.

---

## Cómo se produce el drift en inferencia

El `DriftTracker` singleton recibe actualizaciones de dos orígenes:

| Origen | Método | Cuándo emite |
|---|---|---|
| `POST /train/` | `update_batch(features)` | Inmediatamente después de cada batch |
| `POST /infer/` | `update_single(feature_vec)` | Después de cada 50 peticiones de inferencia |

La actualización EMA (α = 0.05) actualiza la referencia de forma suave. Un desplazamiento brusco como el que genera el seeder (> 2σ) eleva `pipeline_data_drift_score` a valores > 0.5 y dispara la alerta `DataDriftDetected`.

---

## Simular drift manualmente

El seeder activa el drift automáticamente a los `DRIFT_ONSET_AFTER_S` segundos (por defecto 120).  
Para forzarlo de inmediato, cierra la ventana del seeder y ábrela con:

```powershell
$env:API_URL             = "http://localhost:8000"
$env:DRIFT_ONSET_AFTER_S = "0"
$env:DRIFT_MAGNITUDE     = "3.0"
.venv\Scripts\python services\seeder\seeder.py
```

En unos segundos, `pipeline_data_drift_score` superará 0.5 y se disparará la alerta.  
Las features con mayor drift serán `radius_mean`, `area_mean` y `concavity_worst` (las más discriminativas del dataset breast cancer).
