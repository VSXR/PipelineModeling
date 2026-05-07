import pytest
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed

from conftest import FEATURES_10


def test_infer_returns_200(client: httpx.Client) -> None:
    r = client.post("/infer/", json={"features": FEATURES_10})
    assert r.status_code == 200


def test_infer_prediction_is_binary(client: httpx.Client) -> None:
    body = client.post("/infer/", json={"features": FEATURES_10}).json()
    assert body["prediction"] in (0, 1)


def test_infer_probability_two_classes(client: httpx.Client) -> None:
    body = client.post("/infer/", json={"features": FEATURES_10}).json()
    proba = body["probability"]
    assert len(proba) == 2
    assert abs(sum(proba) - 1.0) < 1e-6


def test_infer_probability_values_in_range(client: httpx.Client) -> None:
    body = client.post("/infer/", json={"features": FEATURES_10}).json()
    for p in body["probability"]:
        assert 0.0 <= p <= 1.0


def test_infer_contains_model_version(client: httpx.Client) -> None:
    body = client.post("/infer/", json={"features": FEATURES_10}).json()
    assert isinstance(body["model_version"], str)
    assert len(body["model_version"]) > 0


def test_infer_echoes_request_id(client: httpx.Client) -> None:
    rid = "test-req-abc123"
    body = client.post("/infer/", json={"features": FEATURES_10, "request_id": rid}).json()
    assert body["request_id"] == rid


def test_infer_null_request_id_when_not_sent(client: httpx.Client) -> None:
    body = client.post("/infer/", json={"features": FEATURES_10}).json()
    assert body["request_id"] is None


@pytest.mark.parametrize("bad_body", [
    {},
    {"features": []},
    {"features": "not_a_list"},
    {"features": [[1, 2], [3, 4]]},  # nested list, not flat
])
def test_infer_invalid_input_returns_422(client: httpx.Client, bad_body: dict) -> None:
    r = client.post("/infer/", json=bad_body)
    assert r.status_code == 422


def test_infer_single_feature_not_rejected_by_schema(client: httpx.Client) -> None:
    # Pydantic accepts any non-empty list — sklearn may reject it with 500
    # if the model was trained on a different feature count, but it must not be 422.
    r = client.post("/infer/", json={"features": [1.0]})
    assert r.status_code != 422


def test_infer_concurrent_requests_all_succeed(client: httpx.Client) -> None:
    def call() -> int:
        return client.post("/infer/", json={"features": FEATURES_10}).status_code

    with ThreadPoolExecutor(max_workers=10) as pool:
        statuses = list(pool.map(lambda _: call(), range(20)))

    assert all(s == 200 for s in statuses)
