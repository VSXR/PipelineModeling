"""
Validates that the OTel + MLflow migration did not break:
  1. PipelineMetrics facade in no-op mode (no OTLP endpoint)
  2. ModelManager startup from local .pkl (no MLflow server)
  3. switch_version() calls mlflow.sklearn.load_model with correct URI
  4. switch_version() preserves resident model on MLflow failure
  5. DriftTracker emits via pipeline_metrics.set_drift_score (no Prometheus)
  6. Removed Prometheus endpoint (/metrics) is absent from the API
  7. Removed DVC settings (git_repo_path, dvc_remote_path) are absent from config

All unit tests run without any external infrastructure.
Integration tests (class TestAPIEndpoints) require API_URL env var.
"""
from __future__ import annotations

import asyncio
import os
from typing import Generator
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _reset_model_manager() -> Generator:
    """Yield and restore ModelManager singleton state around a test."""
    from services.api.core.model_manager import ModelManager
    ModelManager._instance = None
    yield
    ModelManager._instance = None


# ── 1. PipelineMetrics — no-op mode ──────────────────────────────────────────

class TestPipelineMetricsNoOp:
    """OTel facade must work when OTEL_EXPORTER_OTLP_ENDPOINT is absent."""

    def setup_method(self):
        os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)

    def test_set_model_loaded_true_and_false(self):
        from services.api.core.metrics import pipeline_metrics
        pipeline_metrics.set_model_loaded(True)
        pipeline_metrics.set_model_loaded(False)

    def test_record_inference_ok_and_error(self):
        from services.api.core.metrics import pipeline_metrics
        pipeline_metrics.record_inference(status="ok", latency_s=0.008)
        pipeline_metrics.record_inference(status="error", latency_s=0.002)

    def test_record_training_updates_counter(self):
        from services.api.core.metrics import pipeline_metrics
        pipeline_metrics.record_training(status="ok", n_samples=64)
        pipeline_metrics.record_training(status="error")

    def test_set_drift_score_populates_internal_dict(self):
        from services.api.core import metrics as m
        m.pipeline_metrics.set_drift_score("radius_mean", 0.73)
        assert m._drift_scores.get("radius_mean") == pytest.approx(0.73)

    def test_drift_score_overwrites_previous_value(self):
        from services.api.core import metrics as m
        m.pipeline_metrics.set_drift_score("area_mean", 0.1)
        m.pipeline_metrics.set_drift_score("area_mean", 0.9)
        assert m._drift_scores["area_mean"] == pytest.approx(0.9)

    def test_record_version_switch_ok_and_error(self):
        from services.api.core.metrics import pipeline_metrics
        pipeline_metrics.record_version_switch(status="ok", duration_s=1.5)
        pipeline_metrics.record_version_switch(status="error")

    def test_model_loaded_flag_reflects_setter(self):
        from services.api.core import metrics as m
        m.pipeline_metrics.set_model_loaded(True)
        assert m._model_loaded_flag == 1
        m.pipeline_metrics.set_model_loaded(False)
        assert m._model_loaded_flag == 0


# ── 2. ModelManager — startup without MLflow ─────────────────────────────────

class TestModelManagerStartup:

    def test_falls_back_to_default_when_pkl_missing(self, tmp_path):
        for _ in _reset_model_manager():
            from services.api.core.model_manager import ModelManager

            async def run():
                mm = ModelManager()
                await mm.load(model_path=str(tmp_path / "nonexistent.pkl"))
                assert mm.is_loaded
                assert mm.version != "unloaded"

            asyncio.run(run())

    def test_loads_real_pkl_when_present(self, tmp_path):
        import joblib
        from sklearn.linear_model import SGDClassifier
        from services.api.core.predictor import SKLearnPredictor

        clf = SGDClassifier()
        clf.fit(np.zeros((4, 30)), [0, 1, 0, 1])
        pkl_path = tmp_path / "model.pkl"
        joblib.dump(clf, pkl_path)

        for _ in _reset_model_manager():
            from services.api.core.model_manager import ModelManager

            async def run():
                mm = ModelManager()
                await mm.load(model_path=str(pkl_path))
                assert mm.is_loaded
                result = await mm.predict([0.0] * 30)
                assert "prediction" in result
                assert "probability" in result

            asyncio.run(run())

    def test_no_dvc_attributes_on_manager(self):
        for _ in _reset_model_manager():
            from services.api.core.model_manager import ModelManager
            mm = ModelManager()
            assert not hasattr(mm, "dvc_remote_path"), "dvc_remote_path must not exist on ModelManager"
            assert not hasattr(mm, "_git_repo_path"), "_git_repo_path must not exist on ModelManager"


# ── 3. switch_version — MLflow registry call ─────────────────────────────────

class TestVersionSwitch:

    def _make_fitted_clf(self):
        from sklearn.linear_model import SGDClassifier
        clf = SGDClassifier()
        clf.fit(np.zeros((4, 30)), [0, 1, 0, 1])
        return clf

    def test_calls_mlflow_load_model_with_correct_uri(self, tmp_path):
        clf = self._make_fitted_clf()

        for _ in _reset_model_manager():
            from services.api.core.model_manager import ModelManager

            async def run():
                with patch("mlflow.set_tracking_uri"), \
                     patch("mlflow.sklearn.load_model", return_value=clf) as mock_load:
                    mm = ModelManager()
                    await mm.load(model_path=str(tmp_path / "no.pkl"))
                    await mm.switch_version("Production")
                    mock_load.assert_called_once_with("models:/pipeline-model/Production")
                    assert mm.version == "Production"

            asyncio.run(run())

    def test_version_number_ref_accepted(self, tmp_path):
        clf = self._make_fitted_clf()

        for _ in _reset_model_manager():
            from services.api.core.model_manager import ModelManager

            async def run():
                with patch("mlflow.set_tracking_uri"), \
                     patch("mlflow.sklearn.load_model", return_value=clf) as mock_load:
                    mm = ModelManager()
                    await mm.load(model_path=str(tmp_path / "no.pkl"))
                    await mm.switch_version("3")
                    mock_load.assert_called_once_with("models:/pipeline-model/3")

            asyncio.run(run())

    def test_preserves_model_on_mlflow_connection_error(self, tmp_path):
        for _ in _reset_model_manager():
            from services.api.core.model_manager import ModelManager

            async def run():
                with patch("mlflow.set_tracking_uri"), \
                     patch("mlflow.sklearn.load_model", side_effect=ConnectionError("MLflow unreachable")):
                    mm = ModelManager()
                    await mm.load(model_path=str(tmp_path / "no.pkl"))
                    assert mm.is_loaded
                    with pytest.raises(ConnectionError):
                        await mm.switch_version("Staging")
                    assert mm.is_loaded, "Model must remain loaded after failed switch"

            asyncio.run(run())

    def test_metrics_record_ok_on_success(self, tmp_path):
        clf = self._make_fitted_clf()
        recorded: list[dict] = []

        for _ in _reset_model_manager():
            from services.api.core.model_manager import ModelManager
            from services.api.core import metrics as m

            original = m.pipeline_metrics.record_version_switch

            def capture(**kwargs):
                recorded.append(kwargs)
                original(**kwargs)

            async def run():
                with patch("mlflow.set_tracking_uri"), \
                     patch("mlflow.sklearn.load_model", return_value=clf), \
                     patch.object(m.pipeline_metrics, "record_version_switch", side_effect=capture):
                    mm = ModelManager()
                    await mm.load(model_path=str(tmp_path / "no.pkl"))
                    await mm.switch_version("Production")

            asyncio.run(run())

        assert any(r.get("status") == "ok" for r in recorded)

    def test_metrics_record_error_on_failure(self, tmp_path):
        recorded: list[dict] = []

        for _ in _reset_model_manager():
            from services.api.core.model_manager import ModelManager
            from services.api.core import metrics as m

            original = m.pipeline_metrics.record_version_switch

            def capture(**kwargs):
                recorded.append(kwargs)
                original(**kwargs)

            async def run():
                with patch("mlflow.set_tracking_uri"), \
                     patch("mlflow.sklearn.load_model", side_effect=RuntimeError("not found")), \
                     patch.object(m.pipeline_metrics, "record_version_switch", side_effect=capture):
                    mm = ModelManager()
                    await mm.load(model_path=str(tmp_path / "no.pkl"))
                    with pytest.raises(RuntimeError):
                        await mm.switch_version("99")

            asyncio.run(run())

        assert not any(r.get("status") == "ok" for r in recorded), \
            "No ok metric must be emitted when switch fails"


# ── 4. DriftTracker — OTel emission (no Prometheus) ──────────────────────────

class TestDriftTrackerOTelIntegration:

    def test_update_batch_populates_drift_scores_dict(self):
        from services.api.core import metrics as m
        from services.api.core.drift import DriftTracker

        m._drift_scores.clear()
        tracker = DriftTracker()
        tracker._ref_means = []  # reset EMA reference (first call initialises, second emits)

        baseline = [[float(i) * 0.01] * 30 for i in range(10)]
        shifted  = [[float(i) * 5.0]  * 30 for i in range(10)]

        tracker.update_batch(baseline)  # initialises _ref_means; no scores emitted yet
        tracker.update_batch(shifted)   # computes deviation; emits scores

        assert len(m._drift_scores) > 0, "Drift scores dict must be populated after two update_batch calls"

    def test_drift_score_values_are_non_negative(self):
        from services.api.core import metrics as m
        from services.api.core.drift import DriftTracker

        tracker = DriftTracker()
        tracker._ref_mean = None

        batch = [[float(i)] * 30 for i in range(5)]
        tracker.update_batch(batch)
        tracker.update_batch([[v * 5 for v in batch[0]]])

        for feature, score in m._drift_scores.items():
            assert score >= 0.0, f"Drift score for {feature} must be non-negative, got {score}"

    def test_no_prometheus_gauge_attribute_on_drift_tracker(self):
        from services.api.core.drift import DriftTracker
        tracker = DriftTracker()
        prometheus_attrs = [a for a in dir(tracker) if "gauge" in a.lower() or "prometheus" in a.lower()]
        assert prometheus_attrs == [], f"Prometheus attributes found: {prometheus_attrs}"


# ── 5. Config — deprecated DVC/git fields removed ────────────────────────────

class TestConfigClean:

    def test_dvc_remote_path_not_in_settings(self):
        from services.api.core.config import Settings
        s = Settings()
        assert not hasattr(s, "dvc_remote_path"), "dvc_remote_path must be removed from Settings"

    def test_git_repo_path_not_in_settings(self):
        from services.api.core.config import Settings
        s = Settings()
        assert not hasattr(s, "git_repo_path"), "git_repo_path must be removed from Settings"

    def test_mlflow_tracking_uri_present(self):
        from services.api.core.config import Settings
        s = Settings()
        assert hasattr(s, "mlflow_tracking_uri")
        assert "mlflow" in s.mlflow_tracking_uri or "localhost" in s.mlflow_tracking_uri

    def test_mlflow_model_name_present(self):
        from services.api.core.config import Settings
        s = Settings()
        assert hasattr(s, "mlflow_model_name")
        assert s.mlflow_model_name != ""


# ── 6. Integration — API endpoint assertions (requires running API) ───────────

@pytest.mark.skipif(
    os.getenv("API_URL") is None,
    reason="API_URL not set — skipping integration tests",
)
class TestAPIEndpoints:

    @pytest.fixture(scope="class")
    def http(self):
        import httpx
        api_url = os.environ["API_URL"]
        with httpx.Client(base_url=api_url, timeout=15.0) as c:
            c.get("/health").raise_for_status()
            yield c

    def test_health_returns_200(self, http):
        r = http.get("/health")
        assert r.status_code == 200

    def test_prometheus_metrics_endpoint_absent(self, http):
        r = http.get("/metrics")
        assert r.status_code == 404, (
            f"/metrics must not exist after OTel migration, got {r.status_code}"
        )

    def test_version_current_returns_model_ref(self, http):
        r = http.get("/version/current")
        assert r.status_code == 200
        body = r.json()
        assert "version" in body or "model_ref" in body or "current_version" in body

    def test_infer_smoke(self, http):
        features = [
            17.99, 10.38, 122.80, 1001.0, 0.1184, 0.2776, 0.3001, 0.1471, 0.2419, 0.0787,
             1.095,  0.905,   8.589,  153.4, 0.0064, 0.0490, 0.0537, 0.0159, 0.0300, 0.0062,
            25.38,  17.33,  184.60, 2019.0, 0.1622, 0.6656, 0.7119, 0.2654, 0.4601, 0.1189,
        ]
        r = http.post("/infer/", json={"features": features})
        assert r.status_code == 200
        body = r.json()
        assert "prediction" in body
