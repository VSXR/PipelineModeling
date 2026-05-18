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
    apply_chaos,
    clear_chaos,
    list_versions,
    refresh_chaos,
    refresh_health,
    run_inference,
    run_training,
    switch_version,
    sync_current_version,
)
from .domain import AppState, initial_state
from .network import fetch_register_version

API_URL = os.getenv("API_URL", "http://api:8000").rstrip("/")

N_FEATURES = 30
_GROUPS: dict[str, list[str]] = {
    "Mean": [
        "radius_mean", "texture_mean", "perimeter_mean", "area_mean", "smoothness_mean",
        "compactness_mean", "concavity_mean", "concave_pts_mean", "symmetry_mean", "fracdim_mean",
    ],
    "SE": [
        "radius_se", "texture_se", "perimeter_se", "area_se", "smoothness_se",
        "compactness_se", "concavity_se", "concave_pts_se", "symmetry_se", "fracdim_se",
    ],
    "Worst": [
        "radius_worst", "texture_worst", "perimeter_worst", "area_worst", "smoothness_worst",
        "compactness_worst", "concavity_worst", "concave_pts_worst", "symmetry_worst", "fracdim_worst",
    ],
}
FEAT_NAMES: list[str] = [f for g in _GROUPS.values() for f in g]

_KEY = "app_state"


def _load() -> AppState:
    if _KEY not in st.session_state:
        st.session_state[_KEY] = initial_state()
    return st.session_state[_KEY]


def _save(state: AppState) -> None:
    st.session_state[_KEY] = state


def _hms(value) -> str:
    try:
        return value.strftime("%H:%M:%S")
    except Exception:
        return "—"


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        *, *::before, *::after {
          font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, system-ui, sans-serif !important;
        }

        /* ── Hide sidebar and its toggle ── */
        section[data-testid="stSidebar"] { display: none !important; }
        [data-testid="collapsedControl"]  { display: none !important; }

        /* ── Tabs ── */
        [data-baseweb="tab-list"] {
          gap: 0.2rem !important;
          padding-bottom: 0 !important;
          border-bottom: 1px solid rgba(255,255,255,0.07) !important;
        }
        button[data-baseweb="tab"] {
          font-size: 0.875rem !important;
          font-weight: 600 !important;
          color: #64748b !important;
          padding: 0.55rem 1.1rem !important;
          border-radius: 6px 6px 0 0 !important;
          border-bottom: 2px solid transparent !important;
          transition: color 0.15s, background 0.15s !important;
        }
        button[data-baseweb="tab"]:hover {
          color: #94a3b8 !important;
          background: rgba(255,255,255,0.04) !important;
        }
        button[data-baseweb="tab"][aria-selected="true"] {
          color: #818cf8 !important;
          border-bottom-color: #818cf8 !important;
          background: rgba(129,140,248,0.08) !important;
        }

        /* ── Metrics ── */
        [data-testid="stMetricLabel"] p {
          font-size: 0.7rem !important;
          font-weight: 700 !important;
          text-transform: uppercase !important;
          letter-spacing: 0.09em !important;
          color: #475569 !important;
        }
        [data-testid="stMetricValue"] {
          font-size: 1.9rem !important;
          font-weight: 800 !important;
          letter-spacing: -0.03em !important;
        }

        /* ── Group captions (bold markdown inside st.caption) ── */
        [data-testid="stCaptionContainer"] p {
          font-size: 0.72rem !important;
          font-weight: 500 !important;
          color: #475569 !important;
          letter-spacing: 0.01em !important;
        }
        [data-testid="stCaptionContainer"] strong {
          font-size: 0.68rem !important;
          font-weight: 800 !important;
          text-transform: uppercase !important;
          letter-spacing: 0.1em !important;
          color: #94a3b8 !important;
        }

        /* ── Buttons ── */
        .stButton > button[kind="primary"] {
          background: #6366f1 !important;
          border: none !important;
          border-radius: 8px !important;
          font-weight: 700 !important;
          font-size: 0.875rem !important;
          letter-spacing: 0.02em !important;
          box-shadow: 0 2px 8px rgba(99,102,241,0.35) !important;
          transition: background 0.15s, box-shadow 0.15s, transform 0.1s !important;
        }
        .stButton > button[kind="primary"]:hover {
          background: #4f46e5 !important;
          box-shadow: 0 4px 16px rgba(99,102,241,0.45) !important;
          transform: translateY(-1px) !important;
        }
        .stButton > button[kind="secondary"] {
          border-radius: 8px !important;
          font-weight: 600 !important;
          font-size: 0.875rem !important;
        }

        /* ── Dividers ── */
        hr {
          border-color: rgba(255,255,255,0.07) !important;
          margin: 1.25rem 0 !important;
        }

        /* ── Inputs ── */
        [data-baseweb="input"] > div,
        [data-baseweb="textarea"],
        [data-baseweb="select"] > div {
          border-radius: 8px !important;
        }

        /* ── Expander summary ── */
        [data-testid="stExpander"] summary span p {
          font-weight: 600 !important;
          font-size: 0.875rem !important;
          color: #64748b !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ── file parsers ──────────────────────────────────────────────────────────────

def _parse_infer_csv(f) -> list[list[float]]:
    f.seek(0)
    df = pd.read_csv(f)
    if all(str(c).replace(".", "").lstrip("-").isdigit() for c in df.columns):
        f.seek(0)
        df = pd.read_csv(f, header=None)
    return df.iloc[:, :N_FEATURES].astype(float).values.tolist()


def _parse_infer_json(f) -> list[list[float]]:
    f.seek(0)
    raw = json.load(f)
    if isinstance(raw, list):
        if raw and isinstance(raw[0], dict):
            return [[float(row.get(feat, 0.0)) for feat in FEAT_NAMES] for row in raw]
        return [[float(v) for v in row] for row in raw]
    if isinstance(raw, dict) and "features" in raw:
        return [[float(v) for v in row] for row in raw["features"]]
    raise ValueError('JSON must be an array or {"features": [[...]]}')


def _parse_train_csv(f) -> tuple[list[list[float]], list[int]]:
    f.seek(0)
    df = pd.read_csv(f)
    feat_cols = [c for c in df.columns if str(c).lower() != "label"][:N_FEATURES]
    return df[feat_cols].astype(float).values.tolist(), df["label"].astype(int).tolist()


def _parse_train_json(f) -> tuple[list[list[float]], list[int]]:
    f.seek(0)
    raw = json.load(f)
    if isinstance(raw, dict):
        return (
            [[float(v) for v in row] for row in raw["features"]],
            [int(v) for v in raw["labels"]],
        )
    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        return (
            [[float(row.get(feat, 0.0)) for feat in FEAT_NAMES] for row in raw],
            [int(row["label"]) for row in raw],
        )
    raise ValueError('JSON must be {"features":[[...]],"labels":[...]} or [{...,"label":0},...]')


# ── top header bar ────────────────────────────────────────────────────────────

def _header(state: AppState) -> None:
    col_title, col_status, col_btn = st.columns([7, 1, 1])

    with col_title:
        st.markdown(
            """
            <div style="padding:0.6rem 0 0.4rem">
              <h1 style="font-size:1.6rem;font-weight:800;letter-spacing:-0.04em;
                         color:#f1f5f9;margin:0 0 0.15rem;line-height:1.1">
                PipelineModeling
              </h1>
              <p style="font-size:0.78rem;color:#475569;font-weight:500;margin:0;letter-spacing:0.01em">
                Breast Cancer Wisconsin &nbsp;&middot;&nbsp; SGDClassifier
                &nbsp;&middot;&nbsp; MLflow &nbsp;&middot;&nbsp; OpenTelemetry
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_status:
        st.markdown("<div style='padding-top:1rem'>", unsafe_allow_html=True)
        if state.api.reachable:
            st.success("Online")
        else:
            st.error("Offline")
        st.markdown("</div>", unsafe_allow_html=True)

    with col_btn:
        st.markdown("<div style='padding-top:1.1rem'>", unsafe_allow_html=True)
        if st.button("Refresh", use_container_width=True, key="hdr_refresh"):
            _save(refresh_health(state, API_URL))
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    st.caption(
        "[📚 Swagger](http://localhost:8000/docs) &nbsp;·&nbsp; "
        "[❤️ Health](http://localhost:8000/health) &nbsp;·&nbsp; "
        "[🧪 MLflow](http://localhost:5000) &nbsp;·&nbsp; "
        "[📊 Grafana](http://localhost:3000) &nbsp;·&nbsp; "
        "[📈 Prometheus](http://localhost:9090) &nbsp;·&nbsp; "
        "[🔭 OTel](http://localhost:55679/debug/tracez)"
    )

    if state.last_error:
        st.error(state.last_error)


# ── inference tab ─────────────────────────────────────────────────────────────

def _tab_inference(state: AppState) -> None:
    mode = st.radio(
        "infer_mode",
        ["Form", "File upload"],
        horizontal=True,
        label_visibility="collapsed",
    )

    if mode == "Form":
        features: list[float] = []
        for group_name, group_feats in _GROUPS.items():
            st.caption(f"**{group_name} features**")
            cols = st.columns(5)
            for j, fname in enumerate(group_feats):
                with cols[j % 5]:
                    features.append(
                        st.number_input(fname, value=0.0, step=0.01, format="%.4f", key=f"if_{fname}")
                    )

        req_id = st.text_input("Request ID", placeholder="optional — leave blank for auto", key="if_rid")
        if st.button("Run inference", type="primary", use_container_width=True):
            _save(run_inference(_load(), API_URL, features, req_id or None))
            st.rerun()

    else:
        with st.expander("Download templates"):
            rng = np.random.default_rng(0)
            sample_df = pd.DataFrame(rng.standard_normal((5, N_FEATURES)), columns=FEAT_NAMES)
            c1, c2 = st.columns(2)
            c1.download_button(
                "CSV template", sample_df.to_csv(index=False),
                "infer_template.csv", "text/csv", use_container_width=True,
            )
            c2.download_button(
                "JSON template",
                json.dumps({"features": sample_df.values.tolist()}, indent=2),
                "infer_template.json", "application/json", use_container_width=True,
            )

        uploaded = st.file_uploader("Upload CSV or JSON (30 features per row)", type=["csv", "json"], key="up_infer")
        if uploaded:
            try:
                samples = (
                    _parse_infer_csv(uploaded)
                    if uploaded.name.endswith(".csv")
                    else _parse_infer_json(uploaded)
                )
                st.caption(f"{len(samples)} sample(s) ready")
                if st.button("Run batch inference", type="primary", use_container_width=True):
                    for i, s in enumerate(samples):
                        _save(run_inference(_load(), API_URL, s, str(i)))
                    st.rerun()
            except Exception as exc:
                st.error(str(exc))

    if state.inference_history:
        latest = state.inference_history[-1]
        st.divider()
        c1, c2, c3 = st.columns(3)
        c1.metric("Prediction", "Benign" if latest.prediction == 1 else "Malignant")
        c2.metric("Confidence", f"{latest.confidence:.1%}")
        c3.metric("Request ID", latest.request_id)
        st.bar_chart(
            pd.DataFrame(
                {"Probability": list(latest.probabilities)},
                index=["Class 0 — Malignant", "Class 1 — Benign"],
            ),
            height=150,
            use_container_width=True,
        )

    if len(state.inference_history) > 1:
        st.divider()
        st.caption("History (last 32)")
        st.dataframe(
            pd.DataFrame([
                {
                    "time": _hms(r.checked_at),
                    "prediction": "Benign" if r.prediction == 1 else "Malignant",
                    "confidence": f"{r.confidence:.1%}",
                    "id": r.request_id,
                }
                for r in reversed(state.inference_history)
            ]),
            use_container_width=True,
            hide_index=True,
        )


# ── training tab ──────────────────────────────────────────────────────────────

def _tab_training(state: AppState) -> None:
    mode = st.radio(
        "train_mode",
        ["File upload", "Synthetic batch"],
        horizontal=True,
        label_visibility="collapsed",
    )

    if mode == "File upload":
        with st.expander("Download templates"):
            rng = np.random.default_rng(7)
            feats = rng.standard_normal((6, N_FEATURES))
            labs = (feats[:, 0] > 0).astype(int)
            df = pd.DataFrame(feats, columns=FEAT_NAMES)
            df["label"] = labs
            c1, c2 = st.columns(2)
            c1.download_button(
                "CSV template", df.to_csv(index=False),
                "train_template.csv", "text/csv", use_container_width=True,
            )
            c2.download_button(
                "JSON template",
                json.dumps({"features": feats.tolist(), "labels": labs.tolist()}, indent=2),
                "train_template.json", "application/json", use_container_width=True,
            )

        uploaded = st.file_uploader(
            "Upload labeled CSV or JSON (30 features + label column, 0=malignant 1=benign)",
            type=["csv", "json"],
            key="up_train",
        )
        if uploaded:
            try:
                features, labels = (
                    _parse_train_csv(uploaded)
                    if uploaded.name.endswith(".csv")
                    else _parse_train_json(uploaded)
                )
                n0, n1 = labels.count(0), labels.count(1)
                st.caption(f"{len(features)} samples — class 0 (malignant): {n0}, class 1 (benign): {n1}")
                if st.button("Train", type="primary", use_container_width=True):
                    _save(run_training(_load(), API_URL, features, labels))
                    st.rerun()
            except Exception as exc:
                st.error(str(exc))

    else:
        c1, c2, c3 = st.columns(3)
        batch_size = c1.slider("Batch size", 10, 2000, 200, 10)
        seed = int(c2.number_input("Seed", value=42, min_value=0, step=1))
        noise = c3.slider("Noise", 0.0, 2.0, 0.5, 0.1)

        rng = np.random.default_rng(seed)
        feats = rng.standard_normal((batch_size, N_FEATURES))
        labs = (
            feats[:, 0] + 0.5 * feats[:, 1] + 0.25 * feats[:, 2]
            + rng.standard_normal(batch_size) * noise > 0.5
        ).astype(int)
        n0, n1 = int((labs == 0).sum()), int((labs == 1).sum())
        st.caption(f"{batch_size} samples — class 0: {n0}, class 1: {n1}")

        if st.button("Train on synthetic batch", type="primary", use_container_width=True):
            _save(run_training(_load(), API_URL, feats.tolist(), labs.tolist()))
            st.rerun()

    if state.training_history:
        latest = state.training_history[-1]
        st.divider()
        c1, c2, c3 = st.columns(3)
        c1.metric("Samples trained", latest.samples)
        c2.metric("Model version", latest.model_version)
        c3.metric("Class split (0:1)", f"{latest.class_zero}:{latest.class_one}")

    if len(state.training_history) > 1:
        st.divider()
        st.caption("History (last 32)")
        st.dataframe(
            pd.DataFrame([
                {
                    "time": _hms(r.checked_at),
                    "samples": r.samples,
                    "class_0": r.class_zero,
                    "class_1": r.class_one,
                    "version": r.model_version,
                }
                for r in reversed(state.training_history)
            ]),
            use_container_width=True,
            hide_index=True,
        )


# ── versioning tab ────────────────────────────────────────────────────────────

def _tab_versioning(state: AppState) -> None:
    if not st.session_state.get("ver_list_loaded") and state.api.reachable:
        st.session_state["ver_list_loaded"] = True
        _save(list_versions(state, API_URL))
        state = _load()

    # ── status header ──────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns([1, 1, 1])
    c1.metric("Active version", state.api.model_version or "—")
    c2.metric("Model loaded", "Yes" if state.api.model_loaded else "No")
    c3.metric("Available versions", len(state.version_list) if state.version_list else "—")

    st.divider()

    # ── dynamic version picker ─────────────────────────────────────────────────
    st.caption("**Switch active model version**")

    col_list, col_refresh = st.columns([5, 1])
    with col_refresh:
        if st.button("Refresh list", use_container_width=True, key="ver_refresh"):
            _save(list_versions(_load(), API_URL))
            st.rerun()

    state = _load()

    if state.version_list:
        labels = [v.label() for v in state.version_list]
        versions_by_label = {v.label(): v for v in state.version_list}

        with col_list:
            selected_label = st.selectbox(
                "Select version",
                options=labels,
                key="ver_select",
                label_visibility="collapsed",
            )

        selected = versions_by_label.get(selected_label)
        selected_ref = selected.version if selected else ""

        c_btn, c_manual = st.columns([2, 3])
        with c_btn:
            if st.button(
                f"Switch to v{selected_ref}",
                type="primary",
                disabled=not selected_ref,
                use_container_width=True,
                key="ver_switch_select",
            ):
                _save(switch_version(_load(), API_URL, selected_ref))
                _save(sync_current_version(_load(), API_URL))
                st.rerun()

        with c_manual:
            manual_ref = st.text_input(
                "Or enter version/alias manually",
                placeholder="1 · 2 · Production · Staging",
                key="ver_ref_manual",
                label_visibility="collapsed",
            )
            if manual_ref and st.button(
                "Switch (manual)",
                disabled=not bool(manual_ref),
                use_container_width=True,
                key="ver_switch_manual",
            ):
                _save(switch_version(_load(), API_URL, manual_ref))
                _save(sync_current_version(_load(), API_URL))
                st.rerun()

        # registered versions table
        st.divider()
        st.caption("**Registered versions in MLflow**")
        st.dataframe(
            pd.DataFrame([
                {
                    "ID":                v.version,
                    "Nombre":            v.model_name or "—",
                    "Alias":             ", ".join(v.aliases) if v.aliases else "—",
                    "Fecha de Registro": v.created_at[:19].replace("T", " ") if v.created_at else "—",
                    "Documentación":     v.description or "—",
                }
                for v in state.version_list
            ]),
            use_container_width=True,
            hide_index=True,
        )

    else:
        with col_list:
            if not state.version_list and state.api.reachable:
                st.info("No registered versions found. Click Refresh list or register the current model below.")
            elif not state.api.reachable:
                st.warning("API not reachable — cannot load version list.")

        manual_ref = st.text_input(
            "Switch to version or alias",
            placeholder="1 · 2 · Production · Staging",
            key="ver_ref",
        )
        if st.button("Switch version", type="primary", disabled=not bool(manual_ref), use_container_width=True):
            _save(switch_version(_load(), API_URL, manual_ref))
            _save(sync_current_version(_load(), API_URL))
            st.rerun()

    # ── register ───────────────────────────────────────────────────────────────
    st.divider()
    st.caption("**Register current model to MLflow**")
    st.caption("Promotes the model in memory (after training) to the MLflow Model Registry as a new version.")
    if st.button("Register to MLflow", use_container_width=True):
        try:
            result = fetch_register_version(API_URL)
            st.success(
                f"Registered as MLflow version {result.get('mlflow_version', '?')}."
                " Click Refresh list to see it in the selector."
            )
            _save(list_versions(_load(), API_URL))
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    # ── switch history ─────────────────────────────────────────────────────────
    if state.version_history:
        st.divider()
        st.caption("Switch history (last 32)")
        st.dataframe(
            pd.DataFrame([
                {
                    "time": _hms(r.checked_at),
                    "from": r.previous_version,
                    "to": r.current_version,
                    "status": r.status,
                }
                for r in reversed(state.version_history)
            ]),
            use_container_width=True,
            hide_index=True,
        )


# ── chaos / debug tab ─────────────────────────────────────────────────────────

def _tab_debug(state: AppState) -> None:
    st.caption("Requires `ENABLE_DEBUG_ENDPOINTS=true` in the API container. Changes take effect immediately on live inference.")

    current = state.chaos_history[-1].inference_error_rate if state.chaos_history else 0.0
    c1, c2 = st.columns([1, 2])

    c1.metric("Active error injection rate", f"{current:.0%}")

    with c2:
        rate = st.slider(
            "Inject error rate",
            min_value=0.0,
            max_value=1.0,
            value=current,
            step=0.05,
            format="%.0f%%",
            key="chaos_slider",
        )
        b1, b2, b3 = st.columns(3)
        if b1.button("Apply", type="primary", use_container_width=True):
            _save(apply_chaos(_load(), API_URL, rate))
            st.rerun()
        if b2.button("Reset to 0%", use_container_width=True):
            _save(clear_chaos(_load(), API_URL))
            st.rerun()
        if b3.button("Fetch state", use_container_width=True):
            _save(refresh_chaos(_load(), API_URL))
            st.rerun()

    if state.chaos_history:
        st.divider()
        st.dataframe(
            pd.DataFrame([
                {"time": _hms(r.checked_at), "rate": f"{r.inference_error_rate:.0%}"}
                for r in reversed(state.chaos_history)
            ]),
            use_container_width=True,
            hide_index=True,
        )


# ── entry point ───────────────────────────────────────────────────────────────

def run() -> None:
    st.set_page_config(
        page_title="PipelineModeling",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    _inject_styles()

    state = _load()
    if not state.api.reachable:
        state = refresh_health(state, API_URL)
        _save(state)
    else:
        state = sync_current_version(state, API_URL)
        _save(state)

    _header(state)
    st.divider()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("API", "Online" if state.api.reachable else "Offline")
    c2.metric("Active version", state.api.model_version or "—")
    c3.metric("Model loaded", "Yes" if state.api.model_loaded else "No")
    c4.metric("Inferences", len(state.inference_history))
    c5.metric("Training rounds", len(state.training_history))
    st.divider()

    tab_infer, tab_train, tab_ver, tab_debug = st.tabs(
        ["Inference", "Training", "Versioning", "Chaos / Debug"]
    )
    with tab_infer:
        _tab_inference(state)
    with tab_train:
        _tab_training(state)
    with tab_ver:
        _tab_versioning(state)
    with tab_debug:
        _tab_debug(state)
