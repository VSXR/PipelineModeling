"""
Metrics integration tests.

Metrics are emitted via OpenTelemetry and flow to Prometheus through the
OTel Collector. The /metrics endpoint was removed in the OTel migration.
These tests query Prometheus directly; they skip automatically if the
Prometheus endpoint is unreachable.

Unit-level metric assertions (no infrastructure required) are in:
  test_otel_mlflow_migration.py::TestPipelineMetricsNoOp
"""
import os
import time

import httpx
import pytest

from conftest import FEATURES_30

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")

PIPELINE_METRICS = [
    "pipeline_model_loaded",
    "pipeline_inference_requests_total",
    "pipeline_inference_latency_seconds_bucket",
    "pipeline_training_requests_total",
    "pipeline_training_samples_total",
    "pipeline_data_drift_score",
    "pipeline_version_switches_total",
    "pipeline_model_load_duration_seconds",
]


@pytest.fixture(scope="module")
def prom(client: httpx.Client):
    try:
        r = httpx.get(f"{PROMETHEUS_URL}/-/healthy", timeout=3.0)
        r.raise_for_status()
    except Exception as exc:
        pytest.skip(f"Prometheus not available at {PROMETHEUS_URL} — {exc}")

    with httpx.Client(base_url=PROMETHEUS_URL, timeout=15.0) as prom_client:
        client.post("/infer/", json={"features": FEATURES_30})
        time.sleep(2)
        yield prom_client


def _query(prom_client: httpx.Client, metric: str) -> list:
    r = prom_client.get("/api/v1/query", params={"query": metric})
    r.raise_for_status()
    return r.json().get("data", {}).get("result", [])


def test_metrics_prometheus_reachable(prom):
    r = prom.get("/-/healthy")
    assert r.status_code == 200


def test_inference_counter_in_prometheus(client: httpx.Client, prom):
    before = _query(prom, 'pipeline_inference_requests_total{status="ok"}')
    before_val = float(before[0]["value"][1]) if before else 0.0

    client.post("/infer/", json={"features": FEATURES_30})
    time.sleep(20)

    after = _query(prom, 'pipeline_inference_requests_total{status="ok"}')
    after_val = float(after[0]["value"][1]) if after else 0.0
    assert after_val > before_val


def test_inference_latency_histogram_in_prometheus(prom):
    results = _query(prom, "pipeline_inference_latency_seconds_bucket")
    assert results, "Inference latency histogram not found in Prometheus"


def test_model_loaded_gauge_in_prometheus(prom):
    results = _query(prom, "pipeline_model_loaded")
    if not results:
        pytest.skip("pipeline_model_loaded not yet in Prometheus")
    assert float(results[0]["value"][1]) == 1.0


def test_training_samples_counter_in_prometheus(client: httpx.Client, prom):
    n = 4
    before = _query(prom, "pipeline_training_samples_total")
    before_val = float(before[0]["value"][1]) if before else 0.0

    client.post("/train/", json={
        "features": [[float(i) * 0.1] * 30 for i in range(n)],
        "labels": [i % 2 for i in range(n)],
    })
    time.sleep(20)

    after = _query(prom, "pipeline_training_samples_total")
    after_val = float(after[0]["value"][1]) if after else 0.0
    assert after_val >= before_val + n
