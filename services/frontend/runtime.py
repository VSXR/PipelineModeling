from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from .controller import (
    refresh_health,
    run_inference,
    run_training,
    switch_version,
    sync_current_version,
)
from .domain import AppState, initial_state, set_inference_mode, set_training_mode

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
GRAFANA_URL = os.getenv("GRAFANA_URL", "http://localhost:3000").rstrip("/")
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090").rstrip("/")
N_FEATURES = 30
FEAT_NAMES = [
    "radius_mean", "texture_mean", "perimeter_mean", "area_mean",
    "smoothness_mean", "compactness_mean", "concavity_mean", "concpts_mean",
    "symmetry_mean", "fracdim_mean",
    "radius_se", "texture_se", "perimeter_se", "area_se",
    "smoothness_se", "compactness_se", "concavity_se", "concpts_se",
    "symmetry_se", "fracdim_se",
    "radius_worst", "texture_worst", "perimeter_worst", "area_worst",
    "smoothness_worst", "compactness_worst", "concavity_worst", "concpts_worst",
    "symmetry_worst", "fracdim_worst",
]


def _state_key() -> str:
    return "pm_frontend_state"


def _load_state() -> AppState:
    if _state_key() not in st.session_state:
        st.session_state[_state_key()] = initial_state()
    return st.session_state[_state_key()]


def _store_state(state: AppState) -> None:
    st.session_state[_state_key()] = state


def _fmt_dt(value) -> str:
    if value is None:
        return "—"
    try:
        return value.astimezone().strftime("%d %b %Y %H:%M:%S UTC")
    except Exception:
        return str(value)


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
          --pm-bg: #0b1020;
          --pm-panel: #11182e;
          --pm-panel-2: #151e38;
          --pm-line: rgba(142, 160, 255, 0.18);
          --pm-text: #e8ecff;
          --pm-muted: #9aa6c7;
          --pm-accent: #7c9cff;
          --pm-accent-2: #62e6c5;
          --pm-alert: #ff6a88;
        }
        .stApp {
          background:
            radial-gradient(circle at top left, rgba(124, 156, 255, 0.18), transparent 30%),
            radial-gradient(circle at top right, rgba(98, 230, 197, 0.12), transparent 22%),
            linear-gradient(180deg, #08101c 0%, #09111f 42%, #0b1020 100%);
          color: var(--pm-text);
        }
        .pm-shell {
          border: 1px solid var(--pm-line);
          border-radius: 22px;
          padding: 1rem 1.1rem;
          background: linear-gradient(180deg, rgba(17, 24, 46, 0.96), rgba(14, 20, 38, 0.92));
          box-shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
        }
        .pm-title {
          font-size: 2.4rem;
          font-weight: 800;
          letter-spacing: -0.04em;
          margin-bottom: 0.2rem;
        }
        .pm-subtitle {
          color: var(--pm-muted);
          font-size: 0.95rem;
          margin-bottom: 1rem;
        }
        .pm-card {
          border: 1px solid var(--pm-line);
          border-radius: 18px;
          background: linear-gradient(180deg, var(--pm-panel), var(--pm-panel-2));
          padding: 1rem 1.05rem;
          min-height: 100%;
        }
        .pm-card h4 {
          margin: 0 0 0.35rem 0;
        }
        .pm-kpi {
          font-size: 2rem;
          font-weight: 800;
          line-height: 1;
          letter-spacing: -0.04em;
        }
        .pm-muted { color: var(--pm-muted); }
        .pm-link a {
          color: var(--pm-text) !important;
          text-decoration: none;
          display: block;
          margin-bottom: 0.45rem;
        }
        .pm-link a:hover { color: var(--pm-accent-2) !important; }
        .pm-chip {
          display: inline-block;
          border: 1px solid var(--pm-line);
          border-radius: 999px;
          padding: 0.25rem 0.65rem;
          color: var(--pm-text);
          background: rgba(124, 156, 255, 0.12);
          font-size: 0.77rem;
          font-weight: 600;
          margin-right: 0.35rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _sidebar(state: AppState) -> None:
    with st.sidebar:
        st.markdown("## PipelineModeling")
        st.markdown('<div class="pm-muted">Host-local UI with Docker observability plane</div>', unsafe_allow_html=True)
        st.divider()

        st.markdown("**API status**")
        if state.api.reachable:
            st.success("Reachable")
        else:
            st.error("Unreachable")
        st.markdown(f"**Model**: `{state.api.model_version}`")
        st.markdown(f"**Loaded**: `{str(state.api.model_loaded).lower()}`")
        st.markdown(f"**Checked**: `{_fmt_dt(state.api.checked_at)}`")

        st.divider()
        st.markdown('<div class="pm-link">', unsafe_allow_html=True)
        st.markdown(f"[Grafana]({GRAFANA_URL})")
        st.markdown(f"[Prometheus]({PROMETHEUS_URL})")
        st.markdown(f"[API Docs]({API_URL}/docs)")
        st.markdown("</div>", unsafe_allow_html=True)

        st.divider()
        if st.button("Refresh status", use_container_width=True):
            _store_state(refresh_health(state, API_URL))
            st.rerun()


def _overview_cards(state: AppState) -> None:
    col1, col2, col3, col4 = st.columns(4)
    latest_inference = state.inference_history[-1] if state.inference_history else None
    latest_training = state.training_history[-1] if state.training_history else None
    latest_version = state.version_history[-1] if state.version_history else None

    with col1:
        st.markdown(
            f'<div class="pm-card"><div class="pm-muted">API</div><div class="pm-kpi">{"UP" if state.api.reachable else "DOWN"}</div><div class="pm-muted">{state.api.model_version}</div></div>',
            unsafe_allow_html=True,
        )
    with col2:
        conf = latest_inference.confidence if latest_inference else 0.0
        st.markdown(
            f'<div class="pm-card"><div class="pm-muted">Latest confidence</div><div class="pm-kpi">{conf:.1%}</div><div class="pm-muted">{latest_inference.request_id if latest_inference else "No inference yet"}</div></div>',
            unsafe_allow_html=True,
        )
    with col3:
        samples = latest_training.samples if latest_training else 0
        st.markdown(
            f'<div class="pm-card"><div class="pm-muted">Last training batch</div><div class="pm-kpi">{samples}</div><div class="pm-muted">{_fmt_dt(latest_training.checked_at) if latest_training else "No training yet"}</div></div>',
            unsafe_allow_html=True,
        )
    with col4:
        status = latest_version.status if latest_version else "idle"
        st.markdown(
            f'<div class="pm-card"><div class="pm-muted">Version switch</div><div class="pm-kpi">{status}</div><div class="pm-muted">{latest_version.current_version if latest_version else "No switch yet"}</div></div>',
            unsafe_allow_html=True,
        )


def _timeline_chart(state: AppState) -> None:
    if not state.timeline:
        st.info("No timeline samples yet. Run an inference, a training batch, or refresh the status.")
        return

    frame = pd.DataFrame([
        {
            "timestamp": sample.checked_at,
            "confidence": sample.confidence,
            "latency_ms": sample.latency_ms,
            "training_samples": sample.training_samples,
            "drift_score": sample.drift_score,
            "model_loaded": sample.model_loaded,
        }
        for sample in state.timeline
    ]).sort_values("timestamp")

    st.line_chart(
        frame.set_index("timestamp")[ [col for col in frame.columns if col != "timestamp"] ],
        height=320,
        use_container_width=True,
    )


def _render_probabilities(probabilities: tuple[float, ...]) -> None:
    series = probabilities if len(probabilities) > 1 else (1.0 - probabilities[0], probabilities[0])
    st.bar_chart(pd.DataFrame({"probability": list(series)}, index=["class 0", "class 1"]), height=180)


def _parse_infer_csv(uploaded) -> list[list[float]]:
    uploaded.seek(0)
    df = pd.read_csv(uploaded)
    if all(str(c).replace(".", "").lstrip("-").isdigit() for c in df.columns):
        uploaded.seek(0)
        df = pd.read_csv(uploaded, header=None)
    return df.iloc[:, :N_FEATURES].astype(float).values.tolist()


def _parse_infer_json(uploaded) -> list[list[float]]:
    uploaded.seek(0)
    raw = json.load(uploaded)
    if isinstance(raw, list):
        if raw and isinstance(raw[0], dict):
            return [[float(row.get(feature, 0.0)) for feature in FEAT_NAMES] for row in raw]
        return [[float(value) for value in row] for row in raw]
    if isinstance(raw, dict) and "features" in raw:
        return [[float(value) for value in row] for row in raw["features"]]
    raise ValueError('JSON must be an array or {"features": [[...]]}')


def _parse_train_csv(uploaded) -> tuple[list[list[float]], list[int]]:
    uploaded.seek(0)
    df = pd.read_csv(uploaded)
    feat_cols = [column for column in df.columns if str(column).lower() != "label"][:N_FEATURES]
    return df[feat_cols].astype(float).values.tolist(), df["label"].astype(int).tolist()


def _parse_train_json(uploaded) -> tuple[list[list[float]], list[int]]:
    uploaded.seek(0)
    raw = json.load(uploaded)
    if isinstance(raw, dict):
        return [[float(value) for value in row] for row in raw["features"]], [int(value) for value in raw["labels"]]
    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        return (
            [[float(row.get(feature, 0.0)) for feature in FEAT_NAMES] for row in raw],
            [int(row["label"]) for row in raw],
        )
    raise ValueError('JSON must be {"features":[[...]],"labels":[...]} or [{...,"label":0},...]')


def _main_content(state: AppState) -> None:
    st.markdown('<div class="pm-shell">', unsafe_allow_html=True)
    st.markdown('<div class="pm-title">PipelineModeling</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="pm-subtitle">Declarative UI · host-local runtime · Docker observability plane</div>',
        unsafe_allow_html=True,
    )

    chips = [
        f"API: {'up' if state.api.reachable else 'down'}",
        f"model: {state.api.model_version}",
        f"inferences: {len(state.inference_history)}",
        f"trainings: {len(state.training_history)}",
        f"versions: {len(state.version_history)}",
    ]
    st.markdown("".join(f'<span class="pm-chip">{chip}</span>' for chip in chips), unsafe_allow_html=True)

    if state.last_error:
        st.error(state.last_error)

    _overview_cards(state)
    st.divider()
    _timeline_chart(state)
    st.divider()

    tab_infer, tab_train, tab_version = st.tabs(["Inference", "Training", "Versioning"])

    with tab_infer:
        inference_mode = st.radio(
            "input_mode",
            ["Form", "Upload file (JSON / CSV)"],
            horizontal=True,
            label_visibility="collapsed",
            index=0 if state.inference_mode == "Form" else 1,
            key="pm_inference_mode",
        )
        if inference_mode != state.inference_mode:
            _store_state(set_inference_mode(state, inference_mode))
            state = _load_state()

        if inference_mode == "Form":
            cols = st.columns(5)
            features: list[float] = []
            for index in range(N_FEATURES):
                with cols[index % 5]:
                    features.append(st.number_input(f"f{index}", value=0.0, step=0.1, format="%.3f", key=f"if_{index}"))

            request_id = st.text_input("Request ID (optional)", placeholder="leave blank for auto-generated", key="if_req_id")
            if st.button("Run Inference", type="primary", use_container_width=True):
                new_state = run_inference(_load_state(), API_URL, features, request_id or None)
                _store_state(new_state)
                st.rerun()

            if state.inference_history:
                latest = state.inference_history[-1]
                metric_col, chart_col = st.columns([1, 2])
                with metric_col:
                    st.metric("Prediction", latest.prediction)
                    st.metric("Confidence", f"{latest.confidence:.1%}")
                    st.caption(f"Request {latest.request_id}")
                with chart_col:
                    _render_probabilities(latest.probabilities)
        else:
            left, right = st.columns(2)
            with left:
                st.info("CSV with 30 numeric columns or JSON array / {\"features\": [...]}.")
            with right:
                rng = np.random.default_rng(0)
                sample_df = pd.DataFrame(rng.standard_normal((5, N_FEATURES)), columns=FEAT_NAMES)
                st.download_button("Download sample CSV", sample_df.to_csv(index=False), file_name="sample_inference.csv", mime="text/csv", use_container_width=True)
                st.download_button("Download sample JSON", json.dumps({"features": sample_df.values.tolist()}, indent=2), file_name="sample_inference.json", mime="application/json", use_container_width=True)

            uploaded = st.file_uploader("Drop CSV or JSON here", type=["csv", "json"], key="upload_infer")
            if uploaded:
                try:
                    samples = _parse_infer_csv(uploaded) if uploaded.name.lower().endswith(".csv") else _parse_infer_json(uploaded)
                    if st.button("Run Batch Inference", type="primary", use_container_width=True):
                        for index, sample in enumerate(samples):
                            _store_state(run_inference(_load_state(), API_URL, sample, str(index)))
                        st.rerun()
                    st.success(f"Loaded {len(samples)} samples from {uploaded.name}")
                except Exception as exc:
                    st.error(f"Could not parse file: {exc}")

    with tab_train:
        training_mode = st.radio(
            "train_source",
            ["Upload labeled file (CSV / JSON)", "Generate synthetic batch"],
            horizontal=True,
            label_visibility="collapsed",
            index=0 if state.training_mode == "Upload labeled file (CSV / JSON)" else 1,
            key="pm_training_mode",
        )
        if training_mode != state.training_mode:
            _store_state(set_training_mode(state, training_mode))
            state = _load_state()

        if training_mode == "Upload labeled file (CSV / JSON)":
            left_t, right_t = st.columns(2)
            with left_t:
                st.info("CSV with 30 features plus label, or JSON {\"features\": [...], \"labels\": [...]}.")
            with right_t:
                rng = np.random.default_rng(7)
                sample_features = rng.standard_normal((6, N_FEATURES))
                sample_labels = (sample_features[:, 0] + 0.5 * sample_features[:, 1] > 0.3).astype(int)
                sample_df = pd.DataFrame(sample_features, columns=FEAT_NAMES)
                sample_df["label"] = sample_labels
                st.download_button("Download sample training CSV", sample_df.to_csv(index=False), file_name="sample_training.csv", mime="text/csv", use_container_width=True)
                st.download_button("Download sample training JSON", json.dumps({"features": sample_features.tolist(), "labels": sample_labels.tolist()}, indent=2), file_name="sample_training.json", mime="application/json", use_container_width=True)

            uploaded = st.file_uploader("Drop labeled CSV or JSON here", type=["csv", "json"], key="upload_train")
            if uploaded:
                try:
                    features, labels = _parse_train_csv(uploaded) if uploaded.name.lower().endswith(".csv") else _parse_train_json(uploaded)
                    if st.button("Train Model", type="primary", use_container_width=True):
                        _store_state(run_training(_load_state(), API_URL, features, labels))
                        st.rerun()
                    st.success(f"Loaded {len(features)} samples")
                except Exception as exc:
                    st.error(f"Could not parse file: {exc}")
        else:
            col_a, col_b, col_c = st.columns(3)
            batch_size = col_a.slider("Batch size", 10, 2000, 200, 10)
            random_seed = col_b.number_input("Random seed", value=42, min_value=0, step=1)
            noise = col_c.slider("Noise level", 0.0, 2.0, 0.5, 0.1)
            rng = np.random.default_rng(int(random_seed))
            features = rng.standard_normal((batch_size, N_FEATURES))
            label_noise = rng.standard_normal(batch_size) * noise
            labels = (features[:, 0] + 0.5 * features[:, 1] + 0.25 * features[:, 2] + label_noise > 0.5).astype(int)
            preview = pd.DataFrame(features[:5], columns=FEAT_NAMES)
            preview.insert(0, "#", range(5))
            preview["label"] = labels[:5]
            st.dataframe(preview, use_container_width=True, hide_index=True)
            if st.button("Train on synthetic batch", type="primary", use_container_width=True):
                _store_state(run_training(_load_state(), API_URL, features.tolist(), labels.tolist()))
                st.rerun()

    with tab_version:
        left_v, right_v = st.columns([3, 2])
        with left_v:
            st.markdown("**Active model version**")
            st.code(state.api.model_version, language=None)
            git_ref = st.text_input("git_ref", placeholder="v1.0.0 · main · abc1234", label_visibility="collapsed", key="ver_ref")
            if st.button("Switch Version", type="primary", disabled=not bool(git_ref), use_container_width=True):
                _store_state(switch_version(_load_state(), API_URL, git_ref))
                _store_state(sync_current_version(_load_state(), API_URL))
                st.rerun()
        with right_v:
            st.markdown("**Continuous status**")
            series = pd.DataFrame([
                {"timestamp": sample.checked_at, "model_loaded": sample.model_loaded or 0, "confidence": sample.confidence, "training_samples": sample.training_samples or 0}
                for sample in state.timeline
            ])
            if not series.empty:
                st.line_chart(series.set_index("timestamp"), height=240, use_container_width=True)
            else:
                st.info("No continuous state yet.")

    st.markdown("</div>", unsafe_allow_html=True)


def run() -> None:
    st.set_page_config(page_title="PipelineModeling", page_icon="⚡", layout="wide", initial_sidebar_state="expanded")
    _inject_styles()
    current_state = _load_state()
    if not current_state.api.reachable:
        current_state = refresh_health(current_state, API_URL)
        _store_state(current_state)
    else:
        current_state = sync_current_version(current_state, API_URL)
        _store_state(current_state)

    _sidebar(current_state)
    _main_content(current_state)
