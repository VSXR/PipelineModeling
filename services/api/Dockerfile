# ══════════════════════════════════════════════════════════════════════
#  Stage 1 — Builder: compile deps against a glibc image with gcc
#  Build context: repository root (.)
# ══════════════════════════════════════════════════════════════════════
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       git \
       curl \
    && rm -rf /var/lib/apt/lists/*

COPY services/api/requirements.txt .

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ══════════════════════════════════════════════════════════════════════
#  Stage 2 — Runtime: minimal image without compilers
# ══════════════════════════════════════════════════════════════════════
FROM python:3.11-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       git \
       curl \
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

# ══════════════════════════════════════════════════════════════════════
#  Stage 3 — Standalone: self-contained image with pre-trained model
#  Use this target for cloud deployment (Render, Railway, Fly.io).
#  Trains model.pkl at build time; no volume mount or MLflow required.
# ══════════════════════════════════════════════════════════════════════
FROM runtime AS standalone

USER root

COPY model/ /tmp/model_src/

RUN git -C /tmp/model_src init \
    && git -C /tmp/model_src config user.email "ci@standalone" \
    && git -C /tmp/model_src config user.name "CI" \
    && git -C /tmp/model_src add . \
    && git -C /tmp/model_src commit -m "standalone" --allow-empty \
    && pip install --no-cache-dir -r /tmp/model_src/requirements.txt \
    && cd /tmp/model_src \
    && MLFLOW_TRACKING_URI=file:///tmp/mlruns \
       MLFLOW_MODEL_NAME=pipeline-model \
       GITHUB_REF_NAME=standalone \
       python train.py \
    && cp -r /tmp/model_src/weights/. /app/model/weights/ \
    && chown -R appuser:appuser /app/model/weights \
    && rm -rf /tmp/model_src /tmp/mlruns

USER appuser
