from __future__ import annotations

from dataclasses import replace
from typing import Optional

from .domain import (
    AppState,
    InferenceRecord,
    ServiceHealth,
    TrainingRecord,
    VersionRecord,
    append_inference,
    append_training,
    append_version,
    now_utc,
    update_health_snapshot,
    with_error,
)
from .network import (
    fetch_current_version,
    fetch_health,
    fetch_inference,
    fetch_switch,
    fetch_training,
)


def refresh_health(state: AppState, api_url: str) -> AppState:
    try:
        health = fetch_health(api_url)
        return update_health_snapshot(
            state,
            model_loaded=bool(health.get("model_loaded", False)),
            model_version=str(health.get("model_version", "—")),
            reachable=True,
        )
    except Exception as exc:
        return replace(
            state,
            api=ServiceHealth(reachable=False, status="down", model_loaded=False, model_version="—", checked_at=now_utc()),
            last_error=f"API unreachable: {exc}",
        )


def run_inference(state: AppState, api_url: str, features: list[float], request_id: Optional[str]) -> AppState:
    try:
        result = fetch_inference(api_url, features, request_id)
        record = InferenceRecord(
            request_id=str(result.request_id or request_id or "auto"),
            prediction=int(result.prediction),
            confidence=float(max(result.probability)),
            probabilities=tuple(float(v) for v in result.probability),
            checked_at=now_utc(),
        )
        updated = append_inference(state, record)
        return update_health_snapshot(
            updated,
            model_loaded=True,
            model_version=str(result.model_version),
            reachable=True,
        )
    except Exception as exc:
        return with_error(state, f"Inference failed: {exc}")


def run_training(state: AppState, api_url: str, features: list[list[float]], labels: list[int]) -> AppState:
    try:
        result = fetch_training(api_url, features, labels)
        count_zero = sum(1 for value in labels if int(value) == 0)
        count_one = sum(1 for value in labels if int(value) == 1)
        record = TrainingRecord(
            samples=int(result.samples_trained),
            class_zero=count_zero,
            class_one=count_one,
            model_version=str(result.model_version),
            checked_at=now_utc(),
        )
        updated = append_training(state, record)
        return update_health_snapshot(
            updated,
            model_loaded=True,
            model_version=str(result.model_version),
            reachable=True,
        )
    except Exception as exc:
        return with_error(state, f"Training failed: {exc}")


def switch_version(state: AppState, api_url: str, git_ref: str) -> AppState:
    try:
        result = fetch_switch(api_url, git_ref)
        record = VersionRecord(
            previous_version=str(result.previous_version),
            current_version=str(result.current_version),
            status=str(result.status),
            checked_at=now_utc(),
        )
        updated = append_version(state, record)
        return update_health_snapshot(
            updated,
            model_loaded=True,
            model_version=str(result.current_version),
            reachable=True,
        )
    except Exception as exc:
        return with_error(state, f"Version switch failed: {exc}")


def sync_current_version(state: AppState, api_url: str) -> AppState:
    try:
        current = fetch_current_version(api_url)
        version = current.get("current_version") or current.get("model_version") or current.get("version") or "—"
        loaded = bool(current.get("model_loaded", state.api.model_loaded))
        return update_health_snapshot(state, model_loaded=loaded, model_version=str(version), reachable=True)
    except Exception:
        return state
