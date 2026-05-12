# Observability Stack Integration Tests

## Overview

Tests in `tests/test_observability_stack.py` validate the complete observability pipeline:
- **OTel Collector** exposes Prometheus metrics on `:9464`
- **Prometheus** scrapes the Collector every 15 seconds
- **Grafana** loads Prometheus datasource automatically
- **Pipeline dashboard** is provisioned and queryable
- **Metrics flow** from API → Collector → Prometheus → Grafana

## Prerequisites

1. **Docker Compose Stack Running**:
   ```bash
   # Start all containers (OTel, Prometheus, Grafana, API, MLflow, etc.)
   docker-compose up -d
   
   # Verify services are healthy
   docker-compose ps
   ```

2. **Python Environment**:
   ```bash
   # Ensure test requirements installed
   pip install -r tests/requirements.txt
   ```

3. **Environment Variables** (optional, defaults provided):
   ```bash
   export API_URL=http://localhost:8000
   export OTEL_COLLECTOR_URL=http://localhost:9464
   export PROMETHEUS_URL=http://localhost:9090
   export GRAFANA_URL=http://localhost:3000
   export GF_ADMIN_PASSWORD=admin
   ```

## Running Tests

### Run All Observability Tests
```bash
pytest tests/test_observability_stack.py -v
```

### Run Specific Test Class
```bash
# Collector metrics validation
pytest tests/test_observability_stack.py::TestCollectorMetricsExposition -v

# Prometheus integration
pytest tests/test_observability_stack.py::TestPrometheusIntegration -v

# Grafana provisioning
pytest tests/test_observability_stack.py::TestGrafanaIntegration -v

# Metrics flow validation
pytest tests/test_observability_stack.py::TestMetricsFlowThroughStack -v

# End-to-end test
pytest tests/test_observability_stack.py::TestStackIntegrationEnd2End -v
```

### Run Specific Test
```bash
pytest tests/test_observability_stack.py::TestPrometheusIntegration::test_prometheus_scrapes_otel_collector -v
```

### Run with Output
```bash
# Show all output, stop on first failure
pytest tests/test_observability_stack.py -v -x

# Show all output, continue on failures
pytest tests/test_observability_stack.py -v --tb=short

# Run tests in parallel (requires pytest-xdist)
pytest tests/test_observability_stack.py -v -n auto
```

## Test Classes

### 1. TestCollectorMetricsExposition
**Purpose**: Validates OTel Collector exposes Prometheus metrics

Tests:
- `test_collector_prometheus_endpoint_responds`: Collector `/metrics` is reachable
- `test_collector_metrics_format_valid`: Metrics in valid Prometheus text format

### 2. TestPrometheusIntegration
**Purpose**: Validates Prometheus scrapes and stores metrics

Tests:
- `test_prometheus_is_healthy`: Prometheus health check passes
- `test_prometheus_has_scrape_targets`: At least one target configured
- `test_prometheus_scrapes_otel_collector`: OTel Collector target healthy and scraped
- `test_prometheus_has_pipeline_metrics`: Pipeline metrics stored (if API has run)
- `test_prometheus_stores_inference_latency`: Inference latency histogram available

### 3. TestGrafanaIntegration
**Purpose**: Validates Grafana is configured and provisioned

Tests:
- `test_grafana_is_healthy`: Grafana API responds with OK status
- `test_grafana_has_prometheus_datasource`: Prometheus datasource provisioned
- `test_prometheus_datasource_is_accessible`: Datasource health check passes
- `test_grafana_has_dashboard_provisioned`: `pipeline-overview` dashboard exists
- `test_dashboard_panels_exist`: Dashboard has panels configured
- `test_dashboard_panel_targets_prometheus`: Dashboard panels query Prometheus

### 4. TestMetricsFlowThroughStack
**Purpose**: Validates metrics propagate through the stack

Tests:
- `test_inference_metrics_reach_prometheus`: Inference metrics stored in Prometheus
- `test_inference_latency_histogram_exists`: Latency histogram queryable
- `test_model_loaded_gauge_accessible_from_grafana`: Model loaded gauge queryable via Grafana proxy

**Note**: Warmup fixture performs a test inference to generate metrics

### 5. TestStackIntegrationEnd2End
**Purpose**: Complete flow validation

Tests:
- `test_metrics_flow_from_api_to_grafana`: 4-step validation (API health → Prometheus scrape → Grafana datasource → Dashboard exists)

## Expected Behavior

### Success (All tests pass)
```
TestCollectorMetricsExposition::test_collector_prometheus_endpoint_responds PASSED
TestCollectorMetricsExposition::test_collector_metrics_format_valid PASSED
TestPrometheusIntegration::test_prometheus_is_healthy PASSED
TestPrometheusIntegration::test_prometheus_has_scrape_targets PASSED
TestPrometheusIntegration::test_prometheus_scrapes_otel_collector PASSED
TestPrometheusIntegration::test_prometheus_has_pipeline_metrics SKIPPED (no data yet)
TestPrometheusIntegration::test_prometheus_stores_inference_latency PASSED
TestGrafanaIntegration::test_grafana_is_healthy PASSED
TestGrafanaIntegration::test_grafana_has_prometheus_datasource PASSED
TestGrafanaIntegration::test_prometheus_datasource_is_accessible PASSED
TestGrafanaIntegration::test_grafana_has_dashboard_provisioned PASSED
TestGrafanaIntegration::test_dashboard_panels_exist PASSED
TestGrafanaIntegration::test_dashboard_panel_targets_prometheus PASSED
TestMetricsFlowThroughStack::test_inference_metrics_reach_prometheus PASSED/SKIPPED
TestMetricsFlowThroughStack::test_inference_latency_histogram_exists PASSED
TestMetricsFlowThroughStack::test_model_loaded_gauge_accessible_from_grafana PASSED
TestStackIntegrationEnd2End::test_metrics_flow_from_api_to_grafana PASSED

= 14-16 passed, 0-2 skipped in 3.5s =
```

### Common Failures & Solutions

#### ❌ `test_collector_prometheus_endpoint_responds` fails
**Cause**: Collector not reachable or OTel exporter not configured
```bash
# Solution: Start collector
docker-compose up -d otel-collector
```

#### ❌ `test_prometheus_scrapes_otel_collector` fails (target DOWN)
**Cause**: Collector endpoint unreachable from Prometheus
**Solution**: Verify docker network, check collector logs
```bash
docker logs pipeline_otel_collector
docker network ls
docker network inspect pipelinemodeling_pipeline_net
```

#### ❌ `test_grafana_has_prometheus_datasource` fails
**Cause**: Datasource not provisioned or Grafana not initialized
**Solution**: Restart Grafana to re-read provisioning
```bash
docker-compose restart grafana
```

#### ❌ `test_grafana_has_dashboard_provisioned` fails
**Cause**: Dashboard JSON not found or invalid
**Solution**: Check provisioning folder mounted correctly
```bash
docker exec pipeline_grafana ls /etc/grafana/provisioning/dashboards/
```

## Observability Stack Architecture

```
┌─────────────┐
│   FastAPI   │
│  :8000      │
└─────┬───────┘
      │ (OpenTelemetry OTLP)
      │ grpc://otel-collector:4317
      ▼
┌──────────────────┐
│  OTel Collector  │
│  :9464 (Prom)    │
│  :4317 (OTLP)    │
│  :55679 (ZipKin) │
└─────┬────────────┘
      │ (Prometheus scrape)
      │ http://otel-collector:9464/metrics
      ▼
┌─────────────────┐
│  Prometheus     │
│  :9090          │
│  (scrape: 15s)  │
└────────┬────────┘
         │ (PromQL query)
         │ http://prometheus:9090/api/v1/query
         ▼
┌──────────────────┐
│  Grafana         │
│  :3000           │
│  dashboard:      │
│  pipeline-       │
│  overview        │
└──────────────────┘
```

## Debugging

### Check Collector Metrics
```bash
curl http://localhost:9464/metrics | head -20
```

### Query Prometheus
```bash
# Check targets
curl http://localhost:9090/api/v1/targets

# Query a metric
curl "http://localhost:9090/api/v1/query?query=up"
```

### Check Grafana Provisioning
```bash
# List datasources
curl -u admin:admin http://localhost:3000/api/datasources

# List dashboards
curl -u admin:admin http://localhost:3000/api/dashboards
```

### View Logs
```bash
docker-compose logs -f otel-collector
docker-compose logs -f prometheus
docker-compose logs -f grafana
docker-compose logs -f api
```

## Integration with CI/CD

To run these tests in CI/CD pipeline:

```yaml
# Example GitHub Actions workflow
- name: Start observability stack
  run: docker-compose up -d

- name: Wait for services
  run: |
    curl --retry 5 --retry-delay 2 http://localhost:9090/-/healthy
    curl --retry 5 --retry-delay 2 http://localhost:3000/api/health

- name: Run observability tests
  run: pytest tests/test_observability_stack.py -v --tb=short
```

## Notes

- Tests use realistic defaults for environment variables (localhost:PORT)
- Some tests may SKIP if metrics haven't been generated yet (e.g., first run)
- 15-second scrape interval means allow 15s for metrics to appear in Prometheus
- Warmup fixture in `TestMetricsFlowThroughStack` performs a test inference
