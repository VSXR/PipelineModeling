from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Optional

MAX_HISTORY = 32
MAX_TIMELINE = 96


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ServiceHealth:
    reachable: bool = False
    status: str = "unknown"
    model_loaded: bool = False
    model_version: str = "—"
    checked_at: Optional[datetime] = None


@dataclass(frozen=True)
class InferenceRecord:
    request_id: str
    prediction: int
    confidence: float
    probabilities: tuple[float, ...]
    checked_at: datetime


@dataclass(frozen=True)
class TrainingRecord:
    samples: int
    class_zero: int
    class_one: int
    model_version: str
    checked_at: datetime


@dataclass(frozen=True)
class VersionRecord:
    previous_version: str
    current_version: str
    status: str
    checked_at: datetime


@dataclass(frozen=True)
class TimelineSample:
    checked_at: datetime
    confidence: Optional[float] = None
    latency_ms: Optional[float] = None
    training_samples: Optional[float] = None
    drift_score: Optional[float] = None
    model_loaded: Optional[int] = None


@dataclass(frozen=True)
class AppState:
    api: ServiceHealth = field(default_factory=ServiceHealth)
    inference_history: tuple[InferenceRecord, ...] = field(default_factory=tuple)
    training_history: tuple[TrainingRecord, ...] = field(default_factory=tuple)
    version_history: tuple[VersionRecord, ...] = field(default_factory=tuple)
    timeline: tuple[TimelineSample, ...] = field(default_factory=tuple)
    last_error: str = ""
    selected_tab: str = "Inference"
    inference_mode: str = "Form"
    training_mode: str = "Upload labeled file (CSV / JSON)"


def initial_state() -> AppState:
    return AppState()


def trim_history(items, limit: int):
    return tuple(items[-limit:]) if len(items) > limit else tuple(items)


def with_health(state: AppState, health: ServiceHealth) -> AppState:
    return replace(state, api=health, last_error="")


def with_error(state: AppState, message: str) -> AppState:
    return replace(state, last_error=message)


def set_tab(state: AppState, tab: str) -> AppState:
    return replace(state, selected_tab=tab)


def set_inference_mode(state: AppState, mode: str) -> AppState:
    return replace(state, inference_mode=mode)


def set_training_mode(state: AppState, mode: str) -> AppState:
    return replace(state, training_mode=mode)


def append_inference(state: AppState, record: InferenceRecord) -> AppState:
    return replace(
        state,
        inference_history=trim_history(state.inference_history + (record,), MAX_HISTORY),
        timeline=trim_history(
            state.timeline + (
                TimelineSample(
                    checked_at=record.checked_at,
                    confidence=record.confidence,
                ),
            ),
            MAX_TIMELINE,
        ),
        last_error="",
    )


def append_training(state: AppState, record: TrainingRecord) -> AppState:
    return replace(
        state,
        training_history=trim_history(state.training_history + (record,), MAX_HISTORY),
        timeline=trim_history(
            state.timeline + (
                TimelineSample(
                    checked_at=record.checked_at,
                    training_samples=float(record.samples),
                ),
            ),
            MAX_TIMELINE,
        ),
        last_error="",
    )


def append_version(state: AppState, record: VersionRecord) -> AppState:
    return replace(
        state,
        version_history=trim_history(state.version_history + (record,), MAX_HISTORY),
        timeline=trim_history(
            state.timeline + (
                TimelineSample(
                    checked_at=record.checked_at,
                    model_loaded=1 if record.status == "ok" else 0,
                ),
            ),
            MAX_TIMELINE,
        ),
        last_error="",
    )


def update_health_snapshot(state: AppState, *, model_loaded: bool, model_version: str, reachable: bool = True) -> AppState:
    return replace(
        state,
        api=ServiceHealth(
            reachable=reachable,
            status="ok" if reachable else "down",
            model_loaded=model_loaded,
            model_version=model_version,
            checked_at=now_utc(),
        ),
        timeline=trim_history(
            state.timeline + (
                TimelineSample(
                    checked_at=now_utc(),
                    model_loaded=1 if model_loaded else 0,
                ),
            ),
            MAX_TIMELINE,
        ),
        last_error="",
    )
