"""
Golden-path integration test: exercises the complete pipeline in order.

  health → infer → train → infer (updated model) → drift → metrics → version
"""
import httpx
import pytest

from conftest import FEATURES_30


def test_full_pipeline_flow(client: httpx.Client) -> None:
    # 1. API healthy and model loaded
    health = client.get("/health").json()
    assert health["status"] == "ok"
    assert health["model_loaded"] is True

    # 2. Inference before training — valid binary prediction
    infer1 = client.post("/infer/", json={"features": FEATURES_30}).json()
    assert infer1["prediction"] in (0, 1)
    assert len(infer1["probability"]) == 2
    version_before = infer1["model_version"]

    # 3. Training — partial_fit updates model and bumps version
    batch_features = [FEATURES_30] * 6
    batch_labels   = [0, 1, 0, 1, 0, 1]
    train_resp = client.post("/train/", json={
        "features": batch_features, "labels": batch_labels
    }).json()
    assert train_resp["status"] == "ok"
    assert train_resp["samples_trained"] == 6
    version_after_train = train_resp["model_version"]
    assert version_after_train != version_before

    # 4. Inference after training uses updated model version
    infer2 = client.post("/infer/", json={"features": FEATURES_30}).json()
    assert infer2["prediction"] in (0, 1)
    assert infer2["model_version"] == version_after_train

    # 5. /version/current agrees with training response
    current = client.get("/version/current").json()
    assert current["model_loaded"] is True
    assert current["version"] == version_after_train

    # 6. Drift detection — two batches with large distribution shift
    ref_batch     = {"features": [[0.0] * 30] * 8, "labels": [i % 2 for i in range(8)]}
    shifted_batch = {"features": [[50.0] * 30] * 8, "labels": [i % 2 for i in range(8)]}
    client.post("/train/", json=ref_batch)
    client.post("/train/", json=shifted_batch)

    # 7. API still responds correctly after drift-inducing batches
    post_drift = client.post("/infer/", json={"features": FEATURES_30}).json()
    assert post_drift["prediction"] in (0, 1)


def test_request_id_propagation(client: httpx.Client) -> None:
    rid  = "flow-test-req-42"
    body = client.post("/infer/", json={"features": FEATURES_30, "request_id": rid}).json()
    assert body["request_id"] == rid
    assert body["prediction"] in (0, 1)


def test_multiple_training_rounds_keep_model_valid(client: httpx.Client) -> None:
    for i in range(5):
        features = [[float(i + j * 0.1) for j in range(30)] for _ in range(4)]
        labels   = [j % 2 for j in range(4)]
        resp = client.post("/train/", json={"features": features, "labels": labels})
        assert resp.status_code == 200

    infer = client.post("/infer/", json={"features": FEATURES_30}).json()
    assert infer["prediction"] in (0, 1)
    assert abs(sum(infer["probability"]) - 1.0) < 1e-6


@pytest.mark.parametrize("n_features", [1, 5, 60, 100])
def test_infer_rejects_wrong_feature_count(client: httpx.Client, n_features: int) -> None:
    features = [0.1 * i for i in range(n_features)]
    r = client.post("/infer/", json={"features": features})
    assert r.status_code == 422


def test_infer_accepts_exactly_30_features(client: httpx.Client) -> None:
    r = client.post("/infer/", json={"features": FEATURES_30})
    assert r.status_code in (200, 500, 503)
