import httpx

from conftest import FEATURES_30

EXPECTED_METRICS = [
    "pipeline_model_loaded",
    "pipeline_inference_requests_total",
    "pipeline_inference_latency_seconds",
    "pipeline_training_requests_total",
    "pipeline_training_samples_total",
    "pipeline_data_drift_score",
    "pipeline_version_switches_total",
    "pipeline_model_load_duration_seconds",
]


def test_metrics_returns_200(client: httpx.Client) -> None:
    r = client.get("/metrics")
    assert r.status_code == 200


def test_metrics_content_type_is_prometheus(client: httpx.Client) -> None:
    r = client.get("/metrics")
    assert "text/plain" in r.headers["content-type"]


def test_metrics_contains_all_pipeline_metrics(client: httpx.Client) -> None:
    text = client.get("/metrics").text
    for name in EXPECTED_METRICS:
        assert name in text, f"Missing metric: {name}"


def test_model_loaded_gauge_is_1(client: httpx.Client) -> None:
    text = client.get("/metrics").text
    loaded_lines = [l for l in text.splitlines()
                    if l.startswith("pipeline_model_loaded ")]
    assert loaded_lines, "pipeline_model_loaded gauge not found"
    assert float(loaded_lines[0].split()[-1]) == 1.0


def test_inference_counter_increments(client: httpx.Client) -> None:
    def _get_total() -> float:
        text = client.get("/metrics").text
        lines = [l for l in text.splitlines()
                 if l.startswith('pipeline_inference_requests_total{status="ok"}')]
        return float(lines[0].split()[-1]) if lines else 0.0

    before = _get_total()
    client.post("/infer/", json={"features": FEATURES_30})
    after = _get_total()

    assert after == before + 1.0


def test_training_samples_counter_increments(client: httpx.Client) -> None:
    def _get_total() -> float:
        text = client.get("/metrics").text
        lines = [l for l in text.splitlines()
                 if l.startswith("pipeline_training_samples_total ")]
        return float(lines[0].split()[-1]) if lines else 0.0

    n = 4
    before = _get_total()
    client.post("/train/", json={
        "features": [[float(i) * 0.1] * 30 for i in range(n)],
        "labels":   [i % 2 for i in range(n)],
    })
    after = _get_total()

    assert after == before + n


def test_inference_latency_histogram_present(client: httpx.Client) -> None:
    client.post("/infer/", json={"features": FEATURES_30})
    text = client.get("/metrics").text
    assert "pipeline_inference_latency_seconds_bucket" in text
    assert "pipeline_inference_latency_seconds_count" in text
