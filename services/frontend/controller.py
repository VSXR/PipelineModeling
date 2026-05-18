from __future__ import annotations

from dataclasses import replace
from typing import Optional

from .domain import (
    AppState,
    ChaosRecord,
    InferenceRecord,
    ServiceHealth,
    TrainingRecord,
    VersionInfo,
    VersionRecord,
    append_chaos,
    append_inference,
    append_training,
    append_version,
    now_utc,
    update_health_snapshot,
    with_error,
    with_version_list,
)
from .network import (
    fetch_chaos_state,
    fetch_current_version,
    fetch_health,
    fetch_inference,
    fetch_reset_chaos,
    fetch_set_chaos,
    fetch_switch,
    fetch_training,
    fetch_version_list,
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


def switch_version(state: AppState, api_url: str, model_ref: str) -> AppState:
    try:
        result = fetch_switch(api_url, model_ref)
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
        version = current.get("version") or "—"
        loaded = bool(current.get("model_loaded", state.api.model_loaded))
        return update_health_snapshot(state, model_loaded=loaded, model_version=str(version), reachable=True)
    except Exception:
        return state


def refresh_chaos(state: AppState, api_url: str) -> AppState:
    try:
        data = fetch_chaos_state(api_url)
        rate = float(data.get("chaos_state", {}).get("inference_error_rate", 0.0))
        record = ChaosRecord(inference_error_rate=rate, checked_at=now_utc())
        return append_chaos(state, record)
    except Exception:
        return state


def apply_chaos(state: AppState, api_url: str, rate: float) -> AppState:
    try:
        fetch_set_chaos(api_url, rate)
        record = ChaosRecord(inference_error_rate=rate, checked_at=now_utc())
        return append_chaos(state, record)
    except Exception as exc:
        return with_error(state, f"Chaos set failed: {exc}")


def list_versions(state: AppState, api_url: str) -> AppState:
    try:
        data = fetch_version_list(api_url)
        model_name = str(data.get("model_name", ""))
        entries = tuple(
            VersionInfo(
                version=str(v["version"]),
                aliases=tuple(v.get("aliases") or []),
                status=str(v.get("status", "")),
                created_at=str(v.get("created_at", "")),
                run_id=v.get("run_id"),
                description=str(v.get("description", "")),
                model_name=model_name,
            )
            for v in data.get("versions", [])
        )
        return with_version_list(state, entries)
    except Exception:
        return with_version_list(state, ())


def clear_chaos(state: AppState, api_url: str) -> AppState:
    try:
        fetch_reset_chaos(api_url)
        record = ChaosRecord(inference_error_rate=0.0, checked_at=now_utc())
        return append_chaos(state, record)
    except Exception as exc:
        return with_error(state, f"Chaos reset failed: {exc}")
