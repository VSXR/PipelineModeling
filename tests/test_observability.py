"""
QA validation: observability stack health and telemetry assertions.

Covers:
  HA-07..HA-12  External service health endpoints
  PA-01..PA-10  PromQL metric assertions via the Prometheus HTTP API

All fixtures skip gracefully when the target service is unreachable, so
this file can run safely in a pure-unit environment (no Docker stack active).

PA-08 (drift score elevation) is gated on the DRIFT_VALIDATED=1 environment
variable, which should be set after running:
  python manage.py simulate --scenario drift
"""
from __future__ import annotations

import os

import httpx
import pytest


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def prometheus() -> httpx.Client:
    url = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
    with httpx.Client(base_url=url, timeout=10.0) as c:
        try:
            c.get("/-/ready").raise_for_status()
        except Exception as exc:
            pytest.skip(f"Prometheus not available at {url} — {exc}")
        yield c


@pytest.fixture(scope="session")
def grafana() -> httpx.Client:
    url = os.getenv("GRAFANA_URL", "http://localhost:3000")
    with httpx.Client(base_url=url, timeout=10.0) as c:
        try:
            c.get("/api/health").raise_for_status()
        except Exception as exc:
            pytest.skip(f"Grafana not available at {url} — {exc}")
        yield c


@pytest.fixture(scope="session")
def otel_prom() -> httpx.Client:
    url = os.getenv("OTEL_PROM_URL", "http://localhost:9464")
    with httpx.Client(base_url=url, timeout=10.0) as c:
        try:
            c.get("/metrics").raise_for_status()
        except Exception as exc:
            pytest.skip(f"OTel Prometheus exporter not available at {url} — {exc}")
        yield c


@pytest.fixture(scope="session")
def otel_health() -> httpx.Client:
    url = os.getenv("OTEL_HEALTH_URL", "http://localhost:13133")
    with httpx.Client(base_url=url, timeout=10.0) as c:
        try:
            c.get("/").raise_for_status()
        except Exception as exc:
            pytest.skip(f"OTel health extension not available at {url} — {exc}")
        yield c


@pytest.fixture(scope="session")
def mlflow_http() -> httpx.Client:
    url = os.getenv("MLFLOW_URL", "http://localhost:5000")
    with httpx.Client(base_url=url, timeout=10.0) as c:
        try:
            c.get("/health").raise_for_status()
        except Exception as exc:
            pytest.skip(f"MLflow not available at {url} — {exc}")
        yield c


@pytest.fixture(scope="session")
def frontend_http() -> httpx.Client:
    url = os.getenv("FRONTEND_URL", "http://localhost:8501")
    with httpx.Client(base_url=url, timeout=10.0) as c:
        try:
            c.get("/_stcore/health").raise_for_status()
        except Exception as exc:
            pytest.skip(f"Frontend not available at {url} — {exc}")
        yield c


# ── helpers ───────────────────────────────────────────────────────────────────


def _promql(prom: httpx.Client, query: str) -> list:
    r = prom.get("/api/v1/query", params={"query": query})
    r.raise_for_status()
    data = r.json()
    assert data["status"] == "success", f"Prometheus query returned error: {data}"
    return data["data"]["result"]


def _scalar(result: list) -> float | None:
    """Extract the numeric value from a single-series PromQL instant result."""
    if not result:
        return None
    value = float(result[0]["value"][1])
    return None if value != value else value  # propagate NaN as None


# ── HA-07..HA-12: infrastructure health ──────────────────────────────────────


class TestInfrastructureHealth:

    def test_grafana_health(self, grafana: httpx.Client) -> None:
        r = grafana.get("/api/health")
        assert r.status_code == 200

    def test_prometheus_ready(self, prometheus: httpx.Client) -> None:
        r = prometheus.get("/-/ready")
        assert r.status_code == 200

    def test_otel_prom_exporter_reachable_and_has_inference_metric(
        self, otel_prom: httpx.Client
    ) -> None:
        r = otel_prom.get("/metrics")
        assert r.status_code == 200
        assert "pipeline_inference_requests_total" in r.text

    def test_otel_health_extension(self, otel_health: httpx.Client) -> None:
        r = otel_health.get("/")
        assert r.status_code == 200

    def test_mlflow_health(self, mlflow_http: httpx.Client) -> None:
        r = mlflow_http.get("/health")
        assert r.status_code == 200

    def test_frontend_health(self, frontend_http: httpx.Client) -> None:
        r = frontend_http.get("/_stcore/health")
        assert r.status_code == 200


# ── PA-01..PA-05: baseline metric presence ───────────────────────────────────


class TestPrometheusBaselineMetrics:

    def test_otel_collector_target_up(self, prometheus: httpx.Client) -> None:
        result = _promql(prometheus, 'up{job="otel-collector"}')
        assert result, "Target otel-collector not found in Prometheus — check scrape config"
        assert _scalar(result) == 1.0

    def test_model_loaded_gauge_is_one(self, prometheus: httpx.Client) -> None:
        result = _promql(prometheus, "pipeline_model_loaded")
        assert result, "pipeline_model_loaded metric absent — OTel export may not have flushed yet"
        assert _scalar(result) == 1.0

    def test_inference_requests_counter_positive(self, prometheus: httpx.Client) -> None:
        result = _promql(prometheus, "sum(pipeline_inference_requests_total)")
        assert result, "pipeline_inference_requests_total absent — no inference traffic recorded"
        assert _scalar(result) > 0

    def test_training_samples_counter_positive(self, prometheus: httpx.Client) -> None:
        result = _promql(prometheus, "sum(pipeline_training_samples_total)")
        assert result, "pipeline_training_samples_total absent — no training traffic recorded"
        assert _scalar(result) > 0

    def test_drift_score_series_count_equals_feature_count(
        self, prometheus: httpx.Client
    ) -> None:
        result = _promql(prometheus, "count(pipeline_data_drift_score)")
        if not result:
            pytest.skip(
                "No drift score series present — DriftTracker requires 50+ inferences to flush"
            )
        assert _scalar(result) == 30.0, (
            f"Expected 30 drift score series (one per feature), got {_scalar(result)}"
        )


# ── PA-06..PA-10: performance and operational assertions ─────────────────────


class TestPrometheusOperationalMetrics:

    def test_inference_latency_p99_under_500ms(self, prometheus: httpx.Client) -> None:
        query = (
            "histogram_quantile(0.99, "
            "sum(rate(pipeline_inference_latency_seconds_bucket[5m])) by (le))"
        )
        result = _promql(prometheus, query)
        p99 = _scalar(result) if result else None
        if p99 is None:
            pytest.skip("Insufficient latency histogram data for p99 computation")
        assert p99 < 0.5, f"p99 inference latency {p99 * 1000:.1f}ms exceeds 500ms threshold"

    def test_error_rate_under_1pct(self, prometheus: httpx.Client) -> None:
        num_result = _promql(
            prometheus,
            'sum(rate(pipeline_inference_requests_total{status="error"}[5m]))',
        )
        den_result = _promql(
            prometheus,
            "sum(rate(pipeline_inference_requests_total[5m]))",
        )
        denominator = _scalar(den_result) if den_result else None
        if not denominator:
            pytest.skip("Insufficient inference traffic to compute error rate")
        numerator = _scalar(num_result) or 0.0
        error_rate = numerator / denominator
        assert error_rate < 0.01, (
            f"Error rate {error_rate:.2%} exceeds 1% threshold (chaos mode may be active)"
        )

    @pytest.mark.skipif(
        not os.getenv("DRIFT_VALIDATED"),
        reason=(
            "Set DRIFT_VALIDATED=1 after: python manage.py simulate --scenario drift"
        ),
    )
    def test_drift_score_elevated_after_simulation(
        self, prometheus: httpx.Client
    ) -> None:
        result = _promql(
            prometheus, 'pipeline_data_drift_score{feature="radius_mean"}'
        )
        assert result, "pipeline_data_drift_score for radius_mean absent after drift simulation"
        score = _scalar(result)
        assert score is not None and score > 5.0, (
            f"radius_mean drift score {score:.3f} not elevated — "
            "expected > 5.0 after ×10 feature magnitude shift"
        )

    def test_version_switches_ok_recorded(self, prometheus: httpx.Client) -> None:
        result = _promql(
            prometheus, 'sum(pipeline_version_switches_total{status="ok"})'
        )
        if not result or _scalar(result) == 0:
            pytest.skip(
                "No successful version switches recorded — run POST /version/switch first"
            )
        assert _scalar(result) > 0

    def test_model_load_p99_under_10s(self, prometheus: httpx.Client) -> None:
        query = (
            "histogram_quantile(0.99, "
            "sum(rate(pipeline_model_load_duration_seconds_bucket[5m])) by (le))"
        )
        result = _promql(prometheus, query)
        p99 = _scalar(result) if result else None
        if p99 is None:
            pytest.skip("No model load duration data present")
        assert p99 < 10.0, f"Model load p99 {p99:.2f}s exceeds 10s threshold"
