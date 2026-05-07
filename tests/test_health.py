import httpx


def test_health_returns_200(client: httpx.Client) -> None:
    r = client.get("/health")
    assert r.status_code == 200


def test_health_status_ok(client: httpx.Client) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"


def test_health_model_loaded(client: httpx.Client) -> None:
    body = client.get("/health").json()
    assert body["model_loaded"] is True


def test_health_contains_version(client: httpx.Client) -> None:
    body = client.get("/health").json()
    assert "model_version" in body
    assert isinstance(body["model_version"], str)
    assert len(body["model_version"]) > 0
