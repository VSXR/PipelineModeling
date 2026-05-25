FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY services/api/requirements.txt .

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Model trainer (standalone only) ────────────────────────────────────
# Isolated stage: installs model deps + git, trains model.pkl, then
# only the weights/ artefacts are copied into the final image.
# git is required because train.py calls subprocess("git rev-parse HEAD").
FROM python:3.11-slim AS model-trainer

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

COPY model/ .

RUN pip install --no-cache-dir -r requirements.txt \
    && git init \
    && git config user.email "ci@standalone" \
    && git config user.name "CI" \
    && git add . \
    && git commit -m "standalone" --allow-empty \
    && MLFLOW_TRACKING_URI=file:///tmp/mlruns \
       MLFLOW_MODEL_NAME=pipeline-model \
       GITHUB_REF_NAME=standalone \
       python train.py

# ── Runtime ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

COPY --from=builder /install /usr/local

COPY services/api/ .

RUN mkdir -p /app/model/weights \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--loop", "uvloop", \
     "--log-level", "info", \
     "--access-log"]

# ── Standalone ──────────────────────────────────────────────────────────
# Self-contained image for cloud hosting (Render, Railway, Fly.io).
# No MLflow server or volume mount required at runtime.
FROM runtime AS standalone

USER root

COPY --from=model-trainer /src/weights/ /app/model/weights/

RUN chown -R appuser:appuser /app/model/weights

USER appuser
