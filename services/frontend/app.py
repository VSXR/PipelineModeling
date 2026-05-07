from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st

# ── wrapper import ────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from wrapper.client import PipelineClient  # noqa: E402

# ── constants ─────────────────────────────────────────────────────────────────
API_URL     = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
GRAFANA_URL = os.getenv("GRAFANA_URL", "http://localhost:3000")
N_FEATURES  = 30
FEAT_NAMES  = [
    "radius_mean",      "texture_mean",     "perimeter_mean",  "area_mean",
    "smoothness_mean",  "compactness_mean",  "concavity_mean",  "concpts_mean",
    "symmetry_mean",    "fracdim_mean",
    "radius_se",        "texture_se",        "perimeter_se",    "area_se",
    "smoothness_se",    "compactness_se",    "concavity_se",    "concpts_se",
    "symmetry_se",      "fracdim_se",
    "radius_worst",     "texture_worst",     "perimeter_worst", "area_worst",
    "smoothness_worst", "compactness_worst", "concavity_worst", "concpts_worst",
    "symmetry_worst",   "fracdim_worst",
]

# ── page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PipelineModeling",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* surface cards */
  .pm-card {
    background: linear-gradient(135deg,#1a1d2e 0%,#22263a 100%);
    border: 1px solid #2d3250;
    border-radius: 14px;
    padding: 24px 20px;
    text-align: center;
  }
  /* status badges */
  .badge-ok  { background:#00c48c20; color:#00c48c;
               border:1px solid #00c48c50;
               padding:3px 12px; border-radius:20px; font-size:.78rem; font-weight:600; }
  .badge-err { background:#ff4b4b20; color:#ff4b4b;
               border:1px solid #ff4b4b50;
               padding:3px 12px; border-radius:20px; font-size:.78rem; font-weight:600; }
  /* probability bars */
  .prob-wrap { margin:6px 0; }
  .prob-label{ color:#888; font-size:.75rem; margin-bottom:2px; }
  .prob-bar  { background:#1a1d2e; border-radius:6px; height:16px; overflow:hidden; }
  .prob-c0   { background:linear-gradient(90deg,#667eea,#764ba2);
               height:100%; border-radius:6px; }
  .prob-c1   { background:linear-gradient(90deg,#f093fb,#f5576c);
               height:100%; border-radius:6px; }
  .prob-pct  { font-size:.85rem; font-weight:700; margin-top:2px; }
  /* sidebar nav links */
  .pm-link a { color:#a0aec0 !important; text-decoration:none; font-size:.87rem; }
  .pm-link a:hover { color:#fff !important; }
</style>
""", unsafe_allow_html=True)


# ── async bridge ──────────────────────────────────────────────────────────────
def _run(coro):
    """Execute an async coroutine from Streamlit's synchronous context."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


# ── API calls via wrapper ─────────────────────────────────────────────────────
@st.cache_data(ttl=5)
def api_health() -> dict | None:
    async def _():
        async with PipelineClient(API_URL) as c:
            return await c.health()
    try:
        return _run(_())
    except Exception:
        return None


def api_infer(features: list[float], request_id: Optional[str] = None):
    async def _():
        async with PipelineClient(API_URL) as c:
            return await c.infer(features, request_id)
    return _run(_())


def api_train(features: list[list[float]], labels: list[int]):
    async def _():
        async with PipelineClient(API_URL) as c:
            return await c.train(features, labels)
    return _run(_())


def api_switch(git_ref: str):
    async def _():
        async with PipelineClient(API_URL) as c:
            return await c.switch_version(git_ref)
    return _run(_())


# ── helpers ───────────────────────────────────────────────────────────────────
def _fmt_version(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%d %b %Y  %H:%M UTC")
    except Exception:
        return iso[:26]


def _parse_infer_csv(uploaded) -> list[list[float]]:
    """Accept CSV with or without headers; use first N_FEATURES columns."""
    raw = uploaded.read().decode()
    uploaded.seek(0)
    # Try with header first
    df = pd.read_csv(uploaded)
    uploaded.seek(0)
    # If all column names are numeric-ish, treat as no-header
    if all(str(c).replace(".", "").lstrip("-").isdigit() for c in df.columns):
        df = pd.read_csv(uploaded, header=None)
    return df.iloc[:, :N_FEATURES].astype(float).values.tolist()


def _parse_infer_json(uploaded) -> list[list[float]]:
    raw = json.load(uploaded)
    if isinstance(raw, list):
        if raw and isinstance(raw[0], dict):
            return [[float(r.get(f, 0.0)) for f in FEAT_NAMES] for r in raw]
        return [[float(v) for v in row] for row in raw]
    if isinstance(raw, dict) and "features" in raw:
        return [[float(v) for v in row] for row in raw["features"]]
    raise ValueError('JSON must be an array or {"features": [[…]]}')


def _parse_train_csv(uploaded) -> tuple[list[list[float]], list[int]]:
    df = pd.read_csv(uploaded)
    feat_cols = [c for c in df.columns if str(c).lower() != "label"][:N_FEATURES]
    return (
        df[feat_cols].astype(float).values.tolist(),
        df["label"].astype(int).tolist(),
    )


def _parse_train_json(uploaded) -> tuple[list[list[float]], list[int]]:
    raw = json.load(uploaded)
    if isinstance(raw, dict):
        return (
            [[float(v) for v in row] for row in raw["features"]],
            [int(l) for l in raw["labels"]],
        )
    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        return (
            [[float(r.get(f, 0.0)) for f in FEAT_NAMES] for r in raw],
            [int(r["label"]) for r in raw],
        )
    raise ValueError('JSON must be {"features":[[…]],"labels":[…]} or [{…,"label":0},…]')


def _render_prob_bars(proba: list[float]) -> None:
    p0 = proba[0] if len(proba) > 1 else 1.0 - proba[0]
    p1 = proba[1] if len(proba) > 1 else proba[0]
    st.markdown(f"""
    <div class="prob-wrap">
      <div class="prob-label">Class 0</div>
      <div class="prob-bar"><div class="prob-c0" style="width:{p0*100:.1f}%"></div></div>
      <div class="prob-pct">{p0:.1%}</div>
    </div>
    <div class="prob-wrap">
      <div class="prob-label">Class 1</div>
      <div class="prob-bar"><div class="prob-c1" style="width:{p1*100:.1f}%"></div></div>
      <div class="prob-pct">{p1:.1%}</div>
    </div>
    """, unsafe_allow_html=True)


# ── sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚡ PipelineModeling")
    st.divider()

    health = api_health()
    if health is None:
        st.error("API unreachable at `" + API_URL + "`")
        st.stop()

    loaded = health.get("model_loaded", False)
    badge  = '<span class="badge-ok">READY</span>' if loaded else '<span class="badge-err">NOT LOADED</span>'
    st.markdown(f"**API** &nbsp; {badge}", unsafe_allow_html=True)
    st.markdown(f"**Version**")
    st.code(_fmt_version(health.get("model_version", "—")), language=None)

    st.divider()
    st.markdown(
        '<div class="pm-link">'
        f'<a href="{GRAFANA_URL}" target="_blank">📊 Grafana Dashboard</a><br>'
        f'<a href="{API_URL}/docs" target="_blank">📖 API Docs (Swagger)</a><br>'
        '<a href="http://localhost:9090" target="_blank">🔍 Prometheus</a>'
        "</div>",
        unsafe_allow_html=True,
    )

    st.divider()
    if st.button("🔄 Refresh status", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


# ── main header ───────────────────────────────────────────────────────────────
st.markdown("# PipelineModeling")
st.caption("Inference · Online training · Model versioning — powered by FastAPI + DVC")

tab_infer, tab_train, tab_version = st.tabs(
    ["🔮 &nbsp; Inference", "🧠 &nbsp; Training", "🏷️ &nbsp; Version Control"]
)


# ═══════════════════════════════════════════════════════════════════════════════
#  TAB — INFERENCE
# ═══════════════════════════════════════════════════════════════════════════════
with tab_infer:
    mode = st.radio(
        "input_mode",
        ["Form", "Upload file (JSON / CSV)"],
        horizontal=True,
        label_visibility="collapsed",
    )
    st.divider()

    # ─── Form ──────────────────────────────────────────────────────────────────
    if mode == "Form":
        st.markdown("#### Enter feature values")
        st.caption("Fill in the 10 features and click **Run Inference**.")

        cols = st.columns(5)
        features: list[float] = []
        for i in range(N_FEATURES):
            with cols[i % 5]:
                features.append(
                    st.number_input(f"f{i}", value=0.0, step=0.1,
                                    format="%.3f", key=f"if_{i}")
                )

        req_id = st.text_input(
            "Request ID (optional)",
            placeholder="leave blank for auto-generated",
            key="if_req_id",
        )

        if st.button("▶ Run Inference", type="primary", use_container_width=True):
            with st.spinner("Running…"):
                try:
                    res = api_infer(features, req_id or None)
                    proba = res.probability
                    pred  = res.prediction
                    col_a, col_b, col_c = st.columns([1, 2, 1])

                    with col_a:
                        color = "#f5576c" if pred == 1 else "#667eea"
                        st.markdown(f"""
                        <div class="pm-card">
                          <div style="font-size:3.5rem;color:{color};font-weight:800;line-height:1">
                            {pred}
                          </div>
                          <div style="color:#888;font-size:.78rem;margin-top:6px;letter-spacing:.08em">
                            PREDICTION
                          </div>
                        </div>""", unsafe_allow_html=True)

                    with col_b:
                        st.markdown("**Class probabilities**")
                        _render_prob_bars(proba)

                    with col_c:
                        conf = max(proba)
                        conf_color = "#00c48c" if conf >= 0.75 else "#f6c90e" if conf >= 0.55 else "#ff4b4b"
                        st.markdown(f"""
                        <div class="pm-card">
                          <div style="font-size:2.4rem;color:{conf_color};font-weight:800;line-height:1">
                            {conf:.1%}
                          </div>
                          <div style="color:#888;font-size:.78rem;margin-top:6px;letter-spacing:.08em">
                            CONFIDENCE
                          </div>
                        </div>""", unsafe_allow_html=True)

                    if res.request_id:
                        st.caption(f"Request ID: `{res.request_id}` · Model: `{_fmt_version(res.model_version)}`")

                except Exception as exc:
                    st.error(f"Inference failed: {exc}")

    # ─── Upload ────────────────────────────────────────────────────────────────
    else:
        st.markdown("#### Batch inference from file")

        left, right = st.columns(2)
        with left:
            st.markdown("**Accepted formats**")
            st.info("""\
**CSV** — one row per sample, 10 numeric columns (header optional):
```
f0,f1,f2,f3,f4,f5,f6,f7,f8,f9
0.1,-0.2,0.5,1.0,-0.3,0.8,0.0,-1.2,0.4,0.7
```

**JSON** — array of arrays **or** `{"features":[…]}`:
```json
[[0.1,-0.2,0.5,1.0,-0.3,0.8,0.0,-1.2,0.4,0.7]]
```
""")

        with right:
            st.markdown("**Download a sample file to try**")
            rng_s = np.random.default_rng(0)
            sample_df = pd.DataFrame(
                rng_s.standard_normal((5, N_FEATURES)),
                columns=FEAT_NAMES,
            )
            st.download_button(
                "⬇ sample_inference.csv",
                data=sample_df.to_csv(index=False),
                file_name="sample_inference.csv",
                mime="text/csv",
                use_container_width=True,
            )
            sample_json = json.dumps({"features": sample_df.values.tolist()}, indent=2)
            st.download_button(
                "⬇ sample_inference.json",
                data=sample_json,
                file_name="sample_inference.json",
                mime="application/json",
                use_container_width=True,
            )

        uploaded = st.file_uploader(
            "Drop CSV or JSON here",
            type=["csv", "json"],
            key="upload_infer",
        )

        if uploaded:
            try:
                if uploaded.name.lower().endswith(".csv"):
                    samples = _parse_infer_csv(uploaded)
                else:
                    samples = _parse_infer_json(uploaded)

                st.success(f"Loaded **{len(samples)} samples** from `{uploaded.name}`")

                if st.button("▶ Run Batch Inference", type="primary", use_container_width=True):
                    bar  = st.progress(0.0, text="Starting…")
                    results, errors = [], []
                    total = len(samples)

                    for idx, row in enumerate(samples):
                        try:
                            r = api_infer(row, request_id=str(idx))
                            results.append(r)
                        except Exception as e:
                            errors.append((idx, str(e)))
                        bar.progress((idx + 1) / total, text=f"Sample {idx + 1} / {total}")

                    bar.empty()

                    if errors:
                        st.warning(f"{len(errors)} sample(s) failed")

                    if results:
                        m1, m2, m3 = st.columns(3)
                        m1.metric("Samples processed", len(results))
                        m2.metric("Class 1 predictions", sum(r.prediction == 1 for r in results))
                        m3.metric(
                            "Avg confidence",
                            f"{np.mean([max(r.probability) for r in results]):.1%}",
                        )

                        rows_out = [
                            {
                                "sample": r.request_id,
                                "prediction": r.prediction,
                                "prob_class_0": round(r.probability[0], 4),
                                "prob_class_1": round(r.probability[1], 4) if len(r.probability) > 1 else None,
                                "confidence": f"{max(r.probability):.1%}",
                            }
                            for r in results
                        ]
                        result_df = pd.DataFrame(rows_out)
                        st.dataframe(result_df, use_container_width=True, hide_index=True)
                        st.download_button(
                            "⬇ Download results as CSV",
                            data=result_df.to_csv(index=False),
                            file_name="inference_results.csv",
                            mime="text/csv",
                        )

            except Exception as exc:
                st.error(f"Could not parse file: {exc}")


# ═══════════════════════════════════════════════════════════════════════════════
#  TAB — TRAINING
# ═══════════════════════════════════════════════════════════════════════════════
with tab_train:
    train_mode = st.radio(
        "train_source",
        ["Upload labeled file (CSV / JSON)", "Generate synthetic batch"],
        horizontal=True,
        label_visibility="collapsed",
    )
    st.divider()

    # ─── Upload labeled data ───────────────────────────────────────────────────
    if train_mode == "Upload labeled file (CSV / JSON)":
        st.markdown("#### Upload labeled training data")

        left_t, right_t = st.columns(2)
        with left_t:
            st.markdown("**Accepted formats**")
            st.info("""\
**CSV** — 10 feature columns + `label` column (0 or 1):
```
f0,f1,...,f9,label
0.1,-0.2,...,0.7,1
```

**JSON** — `{"features":[[…]],"labels":[…]}` or array of dicts:
```json
{"features":[[0.1,-0.2,…]],"labels":[1]}
```
""")

        with right_t:
            st.markdown("**Download a sample training file**")
            rng_t = np.random.default_rng(7)
            X_samp = rng_t.standard_normal((6, N_FEATURES))
            y_samp = (X_samp[:, 0] + 0.5 * X_samp[:, 1] > 0.3).astype(int)
            samp_train_df = pd.DataFrame(X_samp, columns=FEAT_NAMES)
            samp_train_df["label"] = y_samp
            st.download_button(
                "⬇ sample_training.csv",
                data=samp_train_df.to_csv(index=False),
                file_name="sample_training.csv",
                mime="text/csv",
                use_container_width=True,
            )
            samp_train_json = json.dumps(
                {"features": X_samp.tolist(), "labels": y_samp.tolist()},
                indent=2,
            )
            st.download_button(
                "⬇ sample_training.json",
                data=samp_train_json,
                file_name="sample_training.json",
                mime="application/json",
                use_container_width=True,
            )

        train_upload = st.file_uploader(
            "Drop labeled CSV or JSON here",
            type=["csv", "json"],
            key="upload_train",
        )

        if train_upload:
            try:
                if train_upload.name.lower().endswith(".csv"):
                    X_up, y_up = _parse_train_csv(train_upload)
                else:
                    X_up, y_up = _parse_train_json(train_upload)

                n0, n1 = y_up.count(0), y_up.count(1)
                st.success(
                    f"Loaded **{len(X_up)} samples** — "
                    f"class 0: {n0} · class 1: {n1}"
                )

                if st.button("▶ Train Model", type="primary",
                             use_container_width=True, key="btn_train_upload"):
                    with st.spinner("Training…"):
                        try:
                            res = api_train(X_up, y_up)
                            st.success(
                                f"Trained on **{res.samples_trained}** samples · "
                                f"new version: `{_fmt_version(res.model_version)}`"
                            )
                            st.cache_data.clear()
                        except Exception as exc:
                            st.error(f"Training failed: {exc}")

            except Exception as exc:
                st.error(f"Could not parse file: {exc}")

    # ─── Synthetic batch ───────────────────────────────────────────────────────
    else:
        st.markdown("#### Generate a synthetic training batch")
        st.caption("Useful for quick experiments or testing the pipeline.")

        p1, p2, p3 = st.columns(3)
        n_syn   = p1.slider("Batch size", 10, 2000, 200, 10)
        seed_syn = p2.number_input("Random seed", value=42, min_value=0, step=1)
        noise_syn = p3.slider("Noise level", 0.0, 2.0, 0.5, 0.1,
                              help="Higher noise → harder classification task")

        rng_syn = np.random.default_rng(int(seed_syn))
        X_syn   = rng_syn.standard_normal((n_syn, N_FEATURES))
        noise_v = rng_syn.standard_normal(n_syn) * noise_syn
        y_syn   = (X_syn[:, 0] + 0.5 * X_syn[:, 1] + 0.25 * X_syn[:, 2] + noise_v > 0.5).astype(int)

        n0s, n1s = int((y_syn == 0).sum()), int((y_syn == 1).sum())
        st.caption(f"Preview: {n_syn} samples · class 0: {n0s} · class 1: {n1s}")

        prev = pd.DataFrame(X_syn[:5], columns=FEAT_NAMES).round(3)
        prev.insert(0, "#", range(5))
        prev["label"] = y_syn[:5]
        st.dataframe(prev, use_container_width=True, hide_index=True)

        if st.button("▶ Train on Synthetic Batch", type="primary",
                     use_container_width=True, key="btn_train_syn"):
            with st.spinner("Training…"):
                try:
                    res = api_train(X_syn.tolist(), y_syn.tolist())
                    st.success(
                        f"Trained on **{res.samples_trained}** samples · "
                        f"new version: `{_fmt_version(res.model_version)}`"
                    )
                    st.cache_data.clear()
                except Exception as exc:
                    st.error(f"Training failed: {exc}")


# ═══════════════════════════════════════════════════════════════════════════════
#  TAB — VERSION CONTROL
# ═══════════════════════════════════════════════════════════════════════════════
with tab_version:
    st.markdown("#### Model Version Control")

    left_v, right_v = st.columns([3, 2])

    with left_v:
        st.markdown("**Active version**")
        st.code(_fmt_version(health.get("model_version", "—")), language=None)

        st.markdown("**Switch to a Git ref** (tag, branch or commit SHA)")
        git_ref = st.text_input(
            "git_ref",
            placeholder="v1.0.0 · v1.2.0 · main · abc1234",
            label_visibility="collapsed",
            key="ver_ref",
        )

        if st.button(
            "🔀 Switch Version",
            type="primary",
            disabled=not bool(git_ref),
            use_container_width=True,
        ):
            with st.spinner(f"Switching to `{git_ref}` — DVC pull may take ~30 s…"):
                try:
                    res = api_switch(git_ref)
                    st.success(
                        f"Switch successful\n\n"
                        f"**Previous:** `{_fmt_version(res.previous_version)}`  \n"
                        f"**Current:**  `{_fmt_version(res.current_version)}`"
                    )
                    st.cache_data.clear()
                    st.rerun()
                except Exception as exc:
                    st.error(f"Version switch failed: {exc}")

        st.caption(
            "List available tags with `git tag -l` in the terminal. "
            "A ref must exist locally; run `git fetch` if the tag comes from GitHub."
        )

    with right_v:
        st.markdown("**How the hot-swap works**")
        st.markdown("""\
1. `git checkout <ref> -- dvc.lock`
2. `dvc pull --force --remote local`
3. `joblib.load` reloads the `.pkl`
4. Model swapped in memory — **no API restart needed**

If the DVC pull fails the current model is preserved and the API
keeps serving normally.
""")

        st.info(
            "After switching, click **Refresh status** in the sidebar "
            "to confirm the new version is active."
        )
