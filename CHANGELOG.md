# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## [0.5.0] — 2026-05-18

### Added
- MLflow version-level enrichment in `model/trainer.py`: `_register()` now writes a professional description via `update_model_version` (dataset context, run ID, registration timestamp, and metrics summary) and four version tags: `run_id`, `registered_at`, `model_name`, `alias`.
- MLflow `promoted_at` tag in `model/promote.py`: set on the version immediately after assigning the `Production` alias.
- `description` field (`str = ""`) in `VersionEntry` Pydantic schema (`services/api/schemas/versioning.py`) and propagated through the full stack: API router → `VersionInfo` domain dataclass → controller → Streamlit runtime.
- `model_name` field in `VersionInfo` domain dataclass, extracted from the top-level `model_name` key in `GET /version/list` response and associated to each entry.
- Model Registry table in the Versioning tab updated to columns: **ID / Nombre / Alias / Fecha de Registro / Documentación**.

### Changed
- `services/frontend/controller.py`: `list_versions()` now extracts `model_name` from the API response and passes both `description` and `model_name` to each `VersionInfo`.

## [0.4.0] — 2026-05-18

### Added
- `GET /version/list` API endpoint: returns all versions registered in MLflow Model Registry with version number, aliases, stage, creation timestamp and run ID.
- `VersionEntry` and `VersionListResponse` Pydantic schemas in `services/api/schemas/versioning.py`.
- Dynamic model version picker in the Versioning tab: a `selectbox` populated from `/version/list` replaces the manual text field. Falls back to manual input when no versions are registered or the API is unreachable.
- Registered versions table in Versioning tab (version, aliases, stage, creation date).
- `VersionInfo` domain dataclass in `services/frontend/domain.py`; `AppState.version_list` field.
- `fetch_version_list` in `services/frontend/network.py` and `list_versions` controller in `services/frontend/controller.py`.
- `list_versions` method in `services/wrapper/client.py`.
- `pytest-playwright>=0.5.0` in `tests/requirements.txt`.
- `tests/test_frontend.py`: 7 E2E tests (FE-01 to FE-07) covering page title, tab count, sidebar API status, inference inputs, versioning controls, traceback absence, and inference submit.
- `fragile` pytest marker (registered in `pytest.ini`) for tests that depend on Streamlit internal DOM structure.
- `manage.py start`: automatically launches the GitHub Actions self-hosted runner in an elevated PowerShell window on Windows (`C:\actions-runner\run.cmd`). Skipped gracefully on non-Windows hosts or when the runner directory is absent.
- `manage.py stop`: terminates `Runner.Listener.exe` and `Runner.Worker.exe` before stopping Docker Compose.
- `manage.py test --frontend`: runs the Playwright E2E suite against `http://localhost:8501`. Requires `playwright install chromium` to be executed once after setup.
- `CHANGELOG.md` following Keep a Changelog format.

## [0.3.0] — 2026-05-11 to 2026-05-15

### Fixed
- `cd.yml` smoke-test: added `touch .env` step before `docker compose up` to satisfy Docker Compose `env_file` validation at parse time (commit `42ad8b8`).
- `ct.yml`: replaced `on: release` trigger with `workflow_call` chain from `ct.yml` deploy job to bypass the GITHUB_TOKEN event-loop restriction.
- `ct.yml`: changed shell to `pwsh -NoProfile -NonInteractive {0}` on the Windows self-hosted runner to avoid PS profile load errors.
- `ct.yml`: replaced `git describe --tags --abbrev=0` (exits 128 on repos without tags) with `git tag --sort=-version:refname | Where-Object ...` (always exits 0).

### Added
- `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true` env block in all three workflows to opt into Node.js 24 ahead of the June 2026 forced migration.

## [0.2.0] — 2026-05-11

### Changed
- Replaced Prometheus direct-push metrics with OpenTelemetry SDK pipeline (OTel Collector → Prometheus scrape).
- Replaced MinIO + DVC artifact store with MLflow SQLite backend (`mlflow.db`) and local artifact directory.
- `git_ref` renamed to `model_ref` in all version tracking surfaces (API, frontend, ct.yml).
- Histogram buckets now use `ExplicitBucketHistogramAggregation` for precise latency boundaries.

### Added
- `otel-collector` service in `docker-compose.yml` with healthcheck disabled and port 13133 exposed.
- `tests/test_observability.py`: 16 observability tests covering Grafana, Prometheus, OTel, and MLflow infrastructure health.

## [0.1.0] — Initial Release

### Added
- FastAPI inference (`/infer/`), incremental training (`/train/`), and versioning (`/version/`) API backed by `SGDClassifier`.
- Streamlit dashboard with Inference, Training, Versioning, and Chaos/Debug tabs.
- MLflow Model Registry integration with hot-swap version switching.
- OpenTelemetry metrics: `pipeline.data.drift_score`, `pipeline.inference.latency_ms`, `pipeline.training.error_count`, `pipeline.model.load_duration_seconds`.
- Grafana + Prometheus observability stack.
- GitHub Actions CI (`ci.yml`), Continuous Training (`ct.yml`), and Continuous Delivery (`cd.yml`) workflows.
- `manage.py` unified CLI (`setup`, `start`, `stop`, `status`, `test`, `simulate`).
- Seeder service for synthetic traffic injection and data drift simulation.
