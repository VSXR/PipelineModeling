import pytest
import httpx

from conftest import FEATURES_30

# Three samples from Breast Cancer Wisconsin (malignant, malignant, benign)
BATCH_FEATURES = [
    [17.99, 10.38, 122.80, 1001.0, 0.1184, 0.2776, 0.3001, 0.1471, 0.2419, 0.0787,
      1.095,  0.905,   8.589,  153.4, 0.0064, 0.0490, 0.0537, 0.0159, 0.0300, 0.0062,
     25.38,  17.33,  184.60, 2019.0, 0.1622, 0.6656, 0.7119, 0.2654, 0.4601, 0.1189],
    [20.57, 17.77, 132.90, 1326.0, 0.0847, 0.0786, 0.0869, 0.0702, 0.1812, 0.0567,
      0.543,  0.734,   3.398,   74.1, 0.0053, 0.0131, 0.0186, 0.0134, 0.0139, 0.0038,
     24.99,  23.41,  158.80, 1956.0, 0.1238, 0.1866, 0.2416, 0.1860, 0.2750, 0.0893],
    [11.42, 20.38,  77.58,  386.1, 0.1425, 0.2839, 0.2414, 0.1052, 0.2597, 0.0974,
      0.498,  1.034,   3.564,   24.5, 0.0062, 0.0532, 0.0474, 0.0177, 0.0186, 0.0056,
     14.91,  26.50,   98.87,  567.7, 0.2098, 0.8663, 0.6869, 0.2575, 0.6638, 0.1730],
]
BATCH_LABELS = [0, 0, 1]


def test_train_returns_200(client: httpx.Client) -> None:
    r = client.post("/train/", json={"features": BATCH_FEATURES, "labels": BATCH_LABELS})
    assert r.status_code == 200


def test_train_status_ok(client: httpx.Client) -> None:
    body = client.post("/train/", json={"features": BATCH_FEATURES, "labels": BATCH_LABELS}).json()
    assert body["status"] == "ok"


def test_train_samples_trained_matches_batch(client: httpx.Client) -> None:
    n = 5
    features = [[float(i + j * 0.01) for j in range(30)] for i in range(n)]
    labels   = [i % 2 for i in range(n)]
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
    r = client.post("/train/", json={"features": [FEATURES_30], "labels": [1]})
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
    normal = [[0.0] * 30] * 4
    labels = [0, 1, 0, 1]
    client.post("/train/", json={"features": normal, "labels": labels})

    shifted = [[10.0] * 30] * 4
    client.post("/train/", json={"features": shifted, "labels": labels})

    metrics_text = client.get("/metrics").text
    assert "pipeline_data_drift_score" in metrics_text


def test_drift_score_high_when_distribution_shifts(client: httpx.Client) -> None:
    ref = [[0.0] * 30] * 10
    labels = [i % 2 for i in range(10)]
    client.post("/train/", json={"features": ref, "labels": labels})

    shifted = [[100.0] * 30] * 10
    client.post("/train/", json={"features": shifted, "labels": labels})

    metrics_text = client.get("/metrics").text
    drift_lines = [
        line for line in metrics_text.splitlines()
        if line.startswith("pipeline_data_drift_score{")
    ]
    assert any(float(line.split()[-1]) > 0.1 for line in drift_lines)
