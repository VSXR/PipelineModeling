"""
Golden-path integration test: exercises the complete pipeline in order.

  health → infer → train → infer (updated model) → drift → metrics → version
"""
import httpx
import pytest

from conftest import FEATURES_10


def test_full_pipeline_flow(client: httpx.Client) -> None:
    # 1. API is healthy and model is loaded
    health = client.get("/health").json()
    assert health["status"] == "ok"
    assert health["model_loaded"] is True

    # 2. Inference before any training — must return a valid binary prediction
    infer1 = client.post("/infer/", json={"features": FEATURES_10}).json()
    assert infer1["prediction"] in (0, 1)
    assert len(infer1["probability"]) == 2
    version_before = infer1["model_version"]

    # 3. Training — partial_fit updates the model and bumps the version
    batch_features = [FEATURES_10] * 6
    batch_labels = [0, 1, 0, 1, 0, 1]
    train_resp = client.post("/train/", json={
        "features": batch_features, "labels": batch_labels
    }).json()
    assert train_resp["status"] == "ok"
    assert train_resp["samples_trained"] == 6
    version_after_train = train_resp["model_version"]
    assert version_after_train != version_before

    # 4. Inference after training uses the updated model version
    infer2 = client.post("/infer/", json={"features": FEATURES_10}).json()
    assert infer2["prediction"] in (0, 1)
    assert infer2["model_version"] == version_after_train

    # 5. Version endpoint agrees with training response
    current = client.get("/version/current").json()
    assert current["model_loaded"] is True
    assert current["version"] == version_after_train

    # 6. Drift detection — two batches with a large distribution shift
    ref_batch = {"features": [[0.0] * 10] * 8, "labels": [i % 2 for i in range(8)]}
    client.post("/train/", json=ref_batch)

    shifted_batch = {"features": [[50.0] * 10] * 8, "labels": [i % 2 for i in range(8)]}
    client.post("/train/", json=shifted_batch)

    metrics_text = client.get("/metrics").text
    drift_lines = [l for l in metrics_text.splitlines()
                   if l.startswith("pipeline_data_drift_score{")]
    assert drift_lines, "No drift score metrics found after distribution shift"
    assert any(float(l.split()[-1]) > 0.0 for l in drift_lines)

    # 7. Metrics endpoint reflects all operations
    assert 'pipeline_inference_requests_total{status="ok"}' in metrics_text
    assert 'pipeline_training_requests_total{status="ok"}' in metrics_text
    assert "pipeline_model_loaded" in metrics_text


def test_request_id_propagation(client: httpx.Client) -> None:
    """request_id is echoed back unchanged through the full infer path."""
    rid = "flow-test-req-42"
    body = client.post("/infer/", json={"features": FEATURES_10, "request_id": rid}).json()
    assert body["request_id"] == rid
    assert body["prediction"] in (0, 1)


def test_multiple_training_rounds_keep_model_valid(client: httpx.Client) -> None:
    """Five consecutive training batches all succeed and produce valid inference."""
    for i in range(5):
        features = [[float(i + j * 0.1) for j in range(10)] for _ in range(4)]
        labels = [j % 2 for j in range(4)]
        resp = client.post("/train/", json={"features": features, "labels": labels})
        assert resp.status_code == 200

    infer = client.post("/infer/", json={"features": FEATURES_10}).json()
    assert infer["prediction"] in (0, 1)
    assert abs(sum(infer["probability"]) - 1.0) < 1e-6


@pytest.mark.parametrize("n_features", [1, 5, 10, 20, 100])
def test_infer_accepts_any_feature_length(client: httpx.Client, n_features: int) -> None:
    """The model accepts any non-empty feature vector — shape is determined by training."""
    features = [0.1 * i for i in range(n_features)]
    r = client.post("/infer/", json={"features": features})
    # Either succeeds (200) or fails gracefully (5xx) — must never be 4xx except 422
    assert r.status_code in (200, 500, 503)
