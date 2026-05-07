import pytest
import httpx

from conftest import FEATURES_10

BATCH_FEATURES = [
    [0.1, -0.2, 0.5, 1.0, -0.3, 0.8, 0.0, -1.2, 0.4, 0.7],
    [1.0, 0.5, -0.3, 0.2, 0.8, -0.1, 0.4, 0.9, -0.6, 0.3],
    [-0.5, 0.3, 1.2, -0.8, 0.6, -0.4, 1.1, 0.2, -0.9, 0.5],
]
BATCH_LABELS = [0, 1, 0]


def test_train_returns_200(client: httpx.Client) -> None:
    r = client.post("/train/", json={"features": BATCH_FEATURES, "labels": BATCH_LABELS})
    assert r.status_code == 200


def test_train_status_ok(client: httpx.Client) -> None:
    body = client.post("/train/", json={"features": BATCH_FEATURES, "labels": BATCH_LABELS}).json()
    assert body["status"] == "ok"


def test_train_samples_trained_matches_batch(client: httpx.Client) -> None:
    n = 5
    features = [[float(i + j) for j in range(10)] for i in range(n)]
    labels = [i % 2 for i in range(n)]
    body = client.post("/train/", json={"features": features, "labels": labels}).json()
    assert body["samples_trained"] == n


def test_train_updates_model_version(client: httpx.Client) -> None:
    version_before = client.post("/train/", json={
        "features": BATCH_FEATURES, "labels": BATCH_LABELS
    }).json()["model_version"]

    version_after = client.post("/train/", json={
        "features": BATCH_FEATURES, "labels": BATCH_LABELS
    }).json()["model_version"]

    assert version_before != version_after


def test_train_version_matches_current(client: httpx.Client) -> None:
    train_version = client.post("/train/", json={
        "features": BATCH_FEATURES, "labels": BATCH_LABELS
    }).json()["model_version"]

    current = client.get("/version/current").json()["version"]
    assert train_version == current


def test_train_single_sample(client: httpx.Client) -> None:
    r = client.post("/train/", json={"features": [FEATURES_10], "labels": [1]})
    assert r.status_code == 200
    assert r.json()["samples_trained"] == 1


@pytest.mark.parametrize("bad_body", [
    {},
    {"features": [[1.0, 2.0]], "labels": [0, 1]},   # length mismatch
    {"features": [], "labels": []},                   # empty batch
    {"features": [[1.0]], "labels": []},              # missing labels
    {"features": [], "labels": [0]},                  # missing features
])
def test_train_invalid_input_returns_422(client: httpx.Client, bad_body: dict) -> None:
    r = client.post("/train/", json=bad_body)
    assert r.status_code == 422


def test_drift_score_emitted_after_two_batches(client: httpx.Client) -> None:
    normal = [[0.0] * 10] * 4
    labels = [0, 1, 0, 1]
    client.post("/train/", json={"features": normal, "labels": labels})

    # Second batch with a large shift to trigger measurable drift
    shifted = [[10.0] * 10] * 4
    client.post("/train/", json={"features": shifted, "labels": labels})

    metrics_text = client.get("/metrics").text
    assert "pipeline_data_drift_score" in metrics_text


def test_drift_score_high_when_distribution_shifts(client: httpx.Client) -> None:
    # Establish reference at 0
    ref = [[0.0] * 10] * 10
    labels = [i % 2 for i in range(10)]
    client.post("/train/", json={"features": ref, "labels": labels})

    # Shift heavily to trigger high drift
    shifted = [[100.0] * 10] * 10
    client.post("/train/", json={"features": shifted, "labels": labels})

    metrics_text = client.get("/metrics").text
    # At least one feature should have a non-zero drift score line
    drift_lines = [l for l in metrics_text.splitlines()
                   if l.startswith("pipeline_data_drift_score{")]
    assert any(float(l.split()[-1]) > 0.1 for l in drift_lines)
