"""
OpenTelemetry metrics facade — vendor-neutral instrumentation.

Exports via OTLP when OTEL_EXPORTER_OTLP_ENDPOINT is set (points to the
otel-collector sidecar in docker-compose, or directly to Datadog/CloudWatch
OTLP endpoints in production). Falls back to no-op when the env var is absent
so unit tests work without any infrastructure.
"""
from __future__ import annotations

import os
from typing import Iterable

from opentelemetry import metrics
from opentelemetry.metrics import Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader


def _build_provider() -> MeterProvider:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return MeterProvider()  # no-op: metrics tracked locally, not exported

    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    exporter = OTLPMetricExporter(endpoint=endpoint, insecure=True)
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=15_000)
    return MeterProvider(metric_readers=[reader])


_provider = _build_provider()
metrics.set_meter_provider(_provider)
_meter = metrics.get_meter("pipeline.api", version="1.0.0")

# ── observable state (gauges backed by callbacks) ─────────────────────────────
_model_loaded_flag: int = 0
_drift_scores: dict[str, float] = {}


def _obs_model_loaded(options) -> Iterable[Observation]:
    yield Observation(_model_loaded_flag)


def _obs_drift_scores(options) -> Iterable[Observation]:
    for feature, score in list(_drift_scores.items()):
        yield Observation(score, {"feature": feature})


_meter.create_observable_gauge(
    "pipeline.model.loaded",
    callbacks=[_obs_model_loaded],
    description="1 when a model is resident in memory, 0 during hot-swap",
)
_meter.create_observable_gauge(
    "pipeline.data.drift_score",
    callbacks=[_obs_drift_scores],
    description="Normalised mean-shift drift score per feature",
)

# ── push instruments ──────────────────────────────────────────────────────────
_inference_requests = _meter.create_counter(
    "pipeline.inference.requests",
    description="Cumulative inference requests by outcome",
)
_inference_latency = _meter.create_histogram(
    "pipeline.inference.latency_seconds",
    unit="s",
    description="End-to-end inference latency (lock + predict + serialise)",
)
_training_requests = _meter.create_counter(
    "pipeline.training.requests",
    description="Cumulative partial-fit requests by outcome",
)
_training_samples = _meter.create_counter(
    "pipeline.training.samples",
    description="Cumulative samples consumed by partial_fit",
)
_version_switches = _meter.create_counter(
    "pipeline.version.switches",
    description="Cumulative model version switches by outcome",
)
_model_load_duration = _meter.create_histogram(
    "pipeline.model.load_duration_seconds",
    unit="s",
    description="Wall-clock time for model load during version switch",
)


# ── public facade (SRP: one object owns all emission logic) ───────────────────
class PipelineMetrics:
    """
    Singleton facade over OTel instruments.
    Callers import `pipeline_metrics` and call typed methods —
    zero coupling to any specific metrics backend.
    """

    def set_model_loaded(self, loaded: bool) -> None:
        global _model_loaded_flag
        _model_loaded_flag = int(loaded)

    def record_inference(self, *, status: str, latency_s: float) -> None:
        _inference_requests.add(1, {"status": status})
        _inference_latency.record(latency_s, {"status": status})

    def record_training(self, *, status: str, n_samples: int = 0) -> None:
        _training_requests.add(1, {"status": status})
        if n_samples > 0:
            _training_samples.add(n_samples)

    def set_drift_score(self, feature: str, score: float) -> None:
        _drift_scores[feature] = score

    def record_version_switch(self, *, status: str, duration_s: float = 0.0) -> None:
        _version_switches.add(1, {"status": status})
        if status == "ok" and duration_s > 0:
            _model_load_duration.record(duration_s)


pipeline_metrics = PipelineMetrics()
