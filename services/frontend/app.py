import os

import httpx
import numpy as np
import streamlit as st

API_URL = os.getenv("API_URL", "http://api:8000").rstrip("/")
GRAFANA_URL = os.getenv("GRAFANA_URL", "http://localhost:3000")
N_FEATURES = 10


def _get(path: str, timeout: float = 5.0) -> tuple[dict | None, str | None]:
    try:
        r = httpx.get(f"{API_URL}{path}", timeout=timeout)
        r.raise_for_status()
        return r.json(), None
    except Exception as exc:
        return None, str(exc)


def _post(path: str, body: dict, timeout: float = 10.0) -> tuple[dict | None, str | None]:
    try:
        r = httpx.post(f"{API_URL}{path}", json=body, timeout=timeout)
        r.raise_for_status()
        return r.json(), None
    except Exception as exc:
        return None, str(exc)


st.set_page_config(page_title="PipelineModeling", layout="wide")
st.title("PipelineModeling — Control Panel")

# ── System Status ─────────────────────────────────────────────────────
st.subheader("System Status")
health, err = _get("/health")
if err:
    st.error(f"API unreachable: {err}")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("API", "OK" if health["status"] == "ok" else "ERROR")
c2.metric("Model Loaded", "Yes" if health["model_loaded"] else "No")
c3.metric("Version", health["model_version"][:22])
c4.markdown(f"[Grafana Dashboard →]({GRAFANA_URL})")

st.divider()

# ── Manual Inference ──────────────────────────────────────────────────
st.subheader("Manual Inference")

feat_cols = st.columns(N_FEATURES)
features = [
    feat_cols[i].number_input(f"f{i}", value=0.0, step=0.1, format="%.2f", key=f"f{i}")
    for i in range(N_FEATURES)
]

if st.button("Run Inference", type="primary"):
    result, err = _post("/infer/", {"features": features})
    if err:
        st.error(f"Inference failed: {err}")
    else:
        r1, r2 = st.columns(2)
        r1.metric("Prediction", result["prediction"])
        r2.metric("Confidence", f"{max(result['probability']):.1%}")

st.divider()

# ── Trigger Training ──────────────────────────────────────────────────
st.subheader("Trigger Training")

t1, t2 = st.columns(2)
n_samples = t1.slider("Batch size", min_value=10, max_value=500, value=50, step=10)
rng_seed = t2.number_input("Random seed", value=42, min_value=0, step=1)

if st.button("Generate Synthetic Batch & Train"):
    rng = np.random.default_rng(int(rng_seed))
    X = rng.standard_normal((n_samples, N_FEATURES))
    y = (X[:, 0] + 0.5 * X[:, 1] + 0.25 * X[:, 2] > 0.5).astype(int)
    with st.spinner("Training…"):
        result, err = _post(
            "/train/",
            {"features": X.tolist(), "labels": y.tolist()},
            timeout=30.0,
        )
    if err:
        st.error(f"Training failed: {err}")
    else:
        st.success(
            f"Trained on {result['samples_trained']} samples — "
            f"new version: {result['model_version'][:22]}"
        )

st.divider()

# ── Version Control ───────────────────────────────────────────────────
st.subheader("Model Version Control")

v_col1, v_col2 = st.columns([3, 1])
git_ref = v_col1.text_input(
    "Git ref (tag, branch, or commit SHA)",
    placeholder="v1.0.0  /  main  /  abc1234",
)

if v_col2.button("Switch Version", disabled=not bool(git_ref)):
    with st.spinner("Fetching weights via DVC (may take 30 – 120 s)…"):
        result, err = _post(
            "/version/switch",
            {"git_ref": git_ref},
            timeout=300.0,
        )
    if err:
        st.error(f"Version switch failed: {err}")
    else:
        st.success(
            f"Switched  {result['previous_version'][:22]}  →  {result['current_version'][:22]}"
        )
