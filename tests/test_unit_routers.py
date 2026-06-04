"""
Unit tests for API routers using FastAPI TestClient.
No external infrastructure required — ModelManager is mocked.
Runs as part of CI (ci.yml) alongside test_otel_mlflow_migration.py.
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)  # force no-op metrics

FEATURES_30 = [
    17.99, 10.38, 122.8, 1001.0, 0.1184, 0.2776, 0.3001, 0.1471,
    0.2419, 0.07871, 1.095, 0.9053, 8.589, 153.4, 0.006399, 0.04904,
    0.05373, 0.01587, 0.03003, 0.006193, 25.38, 17.33, 184.6, 2019.0,
    0.1622, 0.6656, 0.7119, 0.2654, 0.4601, 0.1189,
]


def _make_manager(**overrides) -> MagicMock:
    mm = MagicMock()
    mm.load = AsyncMock()
    mm.is_loaded = True
    mm.version = "v1"
    mm.samples_trained = 42
    mm.predict = AsyncMock(return_value={"prediction": 0, "probability": [0.8, 0.2]})
    mm.partial_fit = AsyncMock()
    mm.switch_version = AsyncMock(return_value="v0")
    mm.register_to_mlflow = AsyncMock(return_value="2")
    for k, v in overrides.items():
        setattr(mm, k, v)
    return mm


@pytest.fixture(scope="module")
def env():
    """Shared (TestClient, mock_manager) for the whole module."""
    mm = _make_manager()
    from main import app  # trigger router imports before patching
    with (
        patch("core.model_manager.ModelManager.get_instance", return_value=mm),
        patch("routers.inference.DriftTracker"),
        patch("routers.training.DriftTracker"),
    ):
        with TestClient(app) as c:
            yield c, mm


# ── Health ─────────────────────────────────────────────────────────────────────

def test_health_ok(env):
    c, _ = env
    r = c.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["model_loaded"] is True


def test_health_not_loaded(env):
    c, mm = env
    mm.is_loaded = False
    try:
        r = c.get("/health")
        assert r.status_code == 503
        assert r.json()["model_loaded"] is False
    finally:
        mm.is_loaded = True


# ── Inference ──────────────────────────────────────────────────────────────────

def test_infer_ok(env):
    c, _ = env
    r = c.post("/infer/", json={"features": FEATURES_30})
    assert r.status_code == 200
    body = r.json()
    assert body["prediction"] in (0, 1)
    assert len(body["probability"]) == 2
    assert "model_version" in body


def test_infer_too_few_features(env):
    c, _ = env
    r = c.post("/infer/", json={"features": [1.0] * 5})
    assert r.status_code == 422


def test_infer_too_many_features(env):
    c, _ = env
    r = c.post("/infer/", json={"features": [1.0] * 31})
    assert r.status_code == 422


def test_infer_runtime_error(env):
    c, mm = env
    original = mm.predict
    mm.predict = AsyncMock(side_effect=RuntimeError("Model not loaded"))
    try:
        r = c.post("/infer/", json={"features": FEATURES_30})
        assert r.status_code == 503
    finally:
        mm.predict = original


# ── Training ───────────────────────────────────────────────────────────────────

def test_train_ok(env):
    c, _ = env
    r = c.post("/train/", json={"features": [FEATURES_30, FEATURES_30], "labels": [0, 1]})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["samples_trained"] == 2


def test_train_length_mismatch(env):
    c, _ = env
    r = c.post("/train/", json={"features": [FEATURES_30], "labels": [0, 1]})
    assert r.status_code == 422


def test_train_empty_batch(env):
    c, _ = env
    r = c.post("/train/", json={"features": [], "labels": []})
    assert r.status_code == 422


# ── Versioning ─────────────────────────────────────────────────────────────────

def test_version_current(env):
    c, _ = env
    r = c.get("/version/current")
    assert r.status_code == 200
    body = r.json()
    assert "version" in body
    assert "model_loaded" in body


def test_version_switch_ok(env):
    c, _ = env
    r = c.post("/version/switch", json={"model_ref": "1"})
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_version_switch_error(env):
    c, mm = env
    original = mm.switch_version
    mm.switch_version = AsyncMock(side_effect=Exception("Version not found in registry"))
    try:
        r = c.post("/version/switch", json={"model_ref": "999"})
        assert r.status_code == 500
    finally:
        mm.switch_version = original


# ── Debug ──────────────────────────────────────────────────────────────────────

def test_debug_chaos_get(env):
    c, _ = env
    r = c.get("/debug/chaos")
    assert r.status_code == 200
    assert "chaos_state" in r.json()


def test_debug_chaos_set(env):
    c, _ = env
    r = c.post("/debug/chaos", json={"inference_error_rate": 0.0})
    assert r.status_code == 200
    assert "chaos_state" in r.json()

def test_train_runtime_error(env):
    c, mm = env
    original = mm.partial_fit
    mm.partial_fit = AsyncMock(side_effect=RuntimeError("Model not loaded"))
    try:
        r = c.post("/train/", json={"features": [FEATURES_30], "labels": [0]})
        assert r.status_code == 503
    finally:
        mm.partial_fit = original


def test_version_register(env):
    c, _ = env
    r = c.post("/version/register")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "mlflow_version" in body


def test_version_list_empty(env):
    c, _ = env
    with patch("mlflow.MlflowClient") as MockClient:
        MockClient.return_value.search_model_versions.return_value = []
        r = c.get("/version/list")
    assert r.status_code == 200
    body = r.json()
    assert body["versions"] == []
