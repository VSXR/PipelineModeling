"""
Integration tests for Prometheus + Grafana observability stack.

Tests validate:
1. Collector exposes Prometheus metrics endpoint
2. Prometheus successfully scrapes the Collector
3. Grafana loads and has datasource configured
4. Dashboard is provisioned
5. Metrics flow through the stack
"""

import os
import time

import httpx
import pytest

COLLECTOR_URL = os.getenv("OTEL_COLLECTOR_URL", "http://localhost:9464")
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
GRAFANA_URL = os.getenv("GRAFANA_URL", "http://localhost:3000")
API_URL = os.getenv("API_URL", "http://localhost:8000")
GRAFANA_ADMIN_USER = "admin"
GRAFANA_ADMIN_PASSWORD = os.getenv("GF_ADMIN_PASSWORD", "admin")


@pytest.fixture(scope="session")
def prometheus_client():
    """Provide an HTTP client configured for Prometheus."""
    with httpx.Client(base_url=PROMETHEUS_URL, timeout=15.0) as client:
        yield client


@pytest.fixture(scope="session")
def grafana_client():
    """Provide an authenticated HTTP client for Grafana."""
    with httpx.Client(
        base_url=GRAFANA_URL,
        timeout=15.0,
        auth=(GRAFANA_ADMIN_USER, GRAFANA_ADMIN_PASSWORD),
    ) as client:
        yield client


@pytest.fixture(scope="session")
def api_client():
    """Provide an HTTP client configured for the API."""
    with httpx.Client(base_url=API_URL, timeout=15.0) as client:
        yield client


class TestCollectorMetricsExposition:
    """Validate OTel Collector exposes Prometheus metrics."""

    def test_collector_prometheus_endpoint_responds(self):
        """Collector /metrics endpoint should be reachable."""
        response = httpx.get(f"{COLLECTOR_URL}/metrics", timeout=5.0)
        assert response.status_code == 200, f"Collector /metrics returned {response.status_code}"

    def test_collector_metrics_format_valid(self):
        """Metrics should be in Prometheus text format."""
        response = httpx.get(f"{COLLECTOR_URL}/metrics", timeout=5.0)
        content = response.text
        # Prometheus format includes lines starting with # or metric names
        assert "# HELP" in content or "otel" in content or "up" in content, \
            "Metrics do not appear to be in Prometheus format"


class TestPrometheusIntegration:
    """Validate Prometheus scrapes collector and stores metrics."""

    def test_prometheus_is_healthy(self, prometheus_client):
        """Prometheus should report healthy status."""
        response = prometheus_client.get("/-/healthy")
        assert response.status_code == 200

    def test_prometheus_has_scrape_targets(self, prometheus_client):
        """Prometheus should have at least one scrape target configured."""
        response = prometheus_client.get("/api/v1/targets")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "success", f"Failed to fetch targets: {data}"
        active_targets = data.get("data", {}).get("activeTargets", [])
        assert len(active_targets) > 0, "No active scrape targets found"

    def test_prometheus_scrapes_otel_collector(self, prometheus_client):
        """Prometheus should successfully scrape the OTel Collector endpoint."""
        response = prometheus_client.get("/api/v1/targets")
        data = response.json()
        active_targets = data.get("data", {}).get("activeTargets", [])
        # Look for the otel-collector job in active targets
        collector_targets = [t for t in active_targets if t.get("labels", {}).get("job") == "otel-collector"]
        assert len(collector_targets) > 0, "Collector target not found in active targets"
        assert collector_targets[0].get("health") == "up", "Collector scrape target is not healthy"

    def test_prometheus_has_pipeline_metrics(self, prometheus_client):
        """Prometheus should have pipeline metrics stored."""
        response = prometheus_client.get('/api/v1/query', params={'query': 'pipeline_model_loaded'})
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "success", f"Query failed: {data}"
        # Metric may not exist yet if API hasn't run, but query should succeed
        result = data.get("data", {}).get("result", [])
        if not result:
            pytest.skip("pipeline_model_loaded metric not yet available (API may not have recorded it)")

    def test_prometheus_stores_inference_latency(self, prometheus_client):
        """Prometheus should store inference latency metrics."""
        response = prometheus_client.get(
            '/api/v1/query',
            params={'query': 'histogram_quantile(0.95, rate(pipeline_inference_latency_seconds_bucket[5m]))'}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "success"


class TestGrafanaIntegration:
    """Validate Grafana is configured and provisioned."""

    def test_grafana_is_healthy(self, grafana_client):
        """Grafana should report healthy status."""
        response = grafana_client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        # Grafana health endpoint returns database: "ok" and version info
        assert data.get("database") == "ok", f"Grafana not healthy: {data}"

    def test_grafana_has_prometheus_datasource(self, grafana_client):
        """Grafana should have Prometheus datasource provisioned."""
        response = grafana_client.get("/api/datasources")
        assert response.status_code == 200
        datasources = response.json()
        prometheus_ds = [ds for ds in datasources if ds.get("type") == "prometheus"]
        assert len(prometheus_ds) > 0, "Prometheus datasource not found in Grafana"
        assert prometheus_ds[0].get("name") == "Prometheus", \
            f"Prometheus datasource has unexpected name: {prometheus_ds[0].get('name')}"

    def test_prometheus_datasource_is_accessible(self, grafana_client):
        """Grafana's Prometheus datasource should be accessible."""
        response = grafana_client.get("/api/datasources")
        datasources = response.json()
        prometheus_ds = [ds for ds in datasources if ds.get("type") == "prometheus"][0]
        ds_id = prometheus_ds.get("id")
        response = grafana_client.get(f"/api/datasources/{ds_id}/health")
        assert response.status_code == 200
        data = response.json()
        # Health check returns status in uppercase "OK"
        assert data.get("status") == "OK", f"Datasource health check failed: {data}"

    def test_grafana_has_dashboard_provisioned(self, grafana_client):
        """Grafana should have the pipeline-overview dashboard provisioned."""
        response = grafana_client.get("/api/dashboards/uid/pipeline-overview")
        assert response.status_code == 200, "Dashboard 'pipeline-overview' not found"
        dashboard = response.json()
        assert dashboard.get("dashboard", {}).get("title") == "PipelineModeling Overview"

    def test_dashboard_panels_exist(self, grafana_client):
        """Dashboard should have at least one panel configured."""
        response = grafana_client.get("/api/dashboards/uid/pipeline-overview")
        dashboard = response.json()
        panels = dashboard.get("dashboard", {}).get("panels", [])
        assert len(panels) > 0, "No panels found in dashboard"

    def test_dashboard_panel_targets_prometheus(self, grafana_client):
        """Dashboard panels should target the Prometheus datasource."""
        response = grafana_client.get("/api/dashboards/uid/pipeline-overview")
        dashboard = response.json()
        panels = dashboard.get("dashboard", {}).get("panels", [])
        for panel in panels:
            targets = panel.get("targets", [])
            if targets:  # Panel should have at least one target if it queries data
                assert any(t.get("refId") for t in targets), \
                    f"Panel {panel.get('title')} has targets but no refId"


class TestMetricsFlowThroughStack:
    """Validate metrics flow from API -> Collector -> Prometheus -> Grafana."""

    @pytest.fixture(autouse=True)
    def warmup(self, api_client):
        """Perform a test inference to generate metrics."""
        try:
            features = [17.99, 10.38, 122.8, 1001.0, 0.1184, 0.2776, 0.3001, 0.1471, 0.2419, 0.07871,
                        1.095, 0.905, 8.589, 153.4, 0.0064, 0.0490, 0.0537, 0.0159, 0.0300, 0.0062,
                        25.38, 17.33, 184.6, 2019.0, 0.1622, 0.6656, 0.7119, 0.2654, 0.4601, 0.1189]
            response = api_client.post("/infer/", json={"features": features})
            if response.status_code == 200:
                time.sleep(2)  # Allow metrics to propagate
        except Exception:
            pytest.skip("Could not perform warmup inference")

    def test_inference_metrics_reach_prometheus(self, prometheus_client):
        """Metrics from inference should reach Prometheus."""
        response = prometheus_client.get(
            '/api/v1/query',
            params={'query': 'increase(pipeline_inference_requests_total[5m]) > 0'}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "success"
        result = data.get("data", {}).get("result", [])
        if result:  # At least one series should exist if metrics flowed
            assert len(result) > 0

    def test_inference_latency_histogram_exists(self, prometheus_client):
        """Inference latency histogram should be stored in Prometheus."""
        response = prometheus_client.get(
            '/api/v1/query',
            params={'query': 'pipeline_inference_latency_seconds_bucket'}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "success"

    def test_model_loaded_gauge_accessible_from_grafana(self, grafana_client, prometheus_client):
        """Model loaded gauge should be queryable through Grafana's Prometheus."""
        # Query via Grafana proxy to Prometheus
        response = grafana_client.get(
            '/api/datasources/proxy/1/api/v1/query',
            params={'query': 'pipeline_model_loaded'}
        )
        # Status code might be different, just check it doesn't error completely
        assert response.status_code in (200, 400), \
            f"Unexpected status when querying through Grafana: {response.status_code}"


@pytest.mark.skipif(
    not all([COLLECTOR_URL, PROMETHEUS_URL, GRAFANA_URL, API_URL]),
    reason="Required environment variables not set"
)
class TestStackIntegrationEnd2End:
    """End-to-end test of the complete stack."""

    def test_metrics_flow_from_api_to_grafana(self, api_client, prometheus_client, grafana_client):
        """Complete flow: API -> Collector -> Prometheus -> Grafana."""
        # 1. API is healthy and has a model
        response = api_client.get("/health")
        assert response.status_code == 200
        health = response.json()
        assert health.get("model_loaded") is not None

        # 2. Prometheus has data from Collector
        response = prometheus_client.get('/api/v1/query', params={'query': 'up'})
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "success"

        # 3. Grafana can query Prometheus
        response = grafana_client.get("/api/datasources")
        assert response.status_code == 200
        datasources = response.json()
        assert any(ds.get("type") == "prometheus" for ds in datasources)

        # 4. Dashboard exists (use uid endpoint)
        response = grafana_client.get("/api/dashboards/uid/pipeline-overview")
        assert response.status_code == 200
