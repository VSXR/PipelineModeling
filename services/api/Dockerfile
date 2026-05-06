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

# API source
COPY services/api/ .

# DVC metadata needed at runtime for version switching
COPY .dvc/config         .dvc/config
COPY dvc.yaml            dvc.yaml
COPY .dvcignore          .dvcignore

RUN mkdir -p /app/model/weights /app/dvc-remote \
    && chown -R appuser:appuser /app

RUN git config --global --add safe.directory /app

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
