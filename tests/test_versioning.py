import httpx


def test_version_current_returns_200(client: httpx.Client) -> None:
    r = client.get("/version/current")
    assert r.status_code == 200


def test_version_current_model_loaded(client: httpx.Client) -> None:
    body = client.get("/version/current").json()
    assert body["model_loaded"] is True


def test_version_current_has_version_string(client: httpx.Client) -> None:
    body = client.get("/version/current").json()
    assert isinstance(body["version"], str)
    assert len(body["version"]) > 0


def test_version_current_consistent_with_health(client: httpx.Client) -> None:
    version = client.get("/version/current").json()["version"]
    health_version = client.get("/health").json()["model_version"]
    assert version == health_version


def test_version_switch_nonexistent_ref_returns_500(client: httpx.Client) -> None:
    r = client.post(
        "/version/switch",
        json={"git_ref": "refs/tags/v999.999.999-does-not-exist"},
        timeout=30.0,
    )
    assert r.status_code == 500


def test_version_switch_empty_ref_returns_422(client: httpx.Client) -> None:
    r = client.post("/version/switch", json={"git_ref": ""})
    assert r.status_code == 422


def test_version_switch_missing_body_returns_422(client: httpx.Client) -> None:
    r = client.post("/version/switch", json={})
    assert r.status_code == 422
