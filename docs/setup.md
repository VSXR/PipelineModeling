# Setup

## Prerrequisitos

| Herramienta | Versión mínima | Verificar |
|---|---|---|
| Python | 3.11 | `python --version` |
| Git | 2.x | `git --version` |
| Docker Desktop | 4.x | `docker compose version` |

> Docker es necesario para MinIO, Prometheus y Grafana. La API, el frontend y el seeder corren en local.

---

## Primera configuración

Un único comando instala las dependencias, crea `.env` y entrena el modelo inicial:

```powershell
.\pipeline.ps1 setup
```

Lo que hace internamente:

1. Crea `.venv` con `python -m venv`
2. Instala todas las dependencias (`services/api`, `frontend`, `seeder`, `model`, `tests`)
3. Fija `pathspec<0.12` (incompatibilidad conocida con DVC 3.51)
4. Copia `.env.example → .env`
5. Entrena `model/weights/model.pkl` si no existe (breast_cancer, 30 features)

---

## Variables de entorno

Todas están en `.env` (generado desde `.env.example`). Las más relevantes:

| Variable | Por defecto | Descripción |
|---|---|---|
| `MODEL_PATH` | ruta local al `.pkl` | Ruta del artefacto del modelo |
| `GIT_REPO_PATH` | raíz del repo | Usado por DVC para `git checkout` en el hot-swap |
| `DVC_REMOTE_PATH` | `./dvc-remote` | Remote local de DVC |
| `MINIO_ACCESS_KEY` | `minioadmin` | Credencial de acceso a MinIO |
| `MINIO_SECRET_KEY` | `minioadmin` | Credencial secreta de MinIO |
| `REQUESTS_PER_SECOND` | `20` | Tasa de inferencia del seeder |
| `INFERENCE_CONCURRENCY` | `10` | Peticiones HTTP en vuelo simultáneas |
| `TRAINING_INTERVAL_S` | `30` | Segundos entre batches de entrenamiento |
| `TRAINING_BATCH_SIZE` | `50` | Muestras por batch |
| `DRIFT_ONSET_AFTER_S` | `120` | Segundos hasta activar la deriva |
| `DRIFT_MAGNITUDE` | `2.0` | Magnitud del desplazamiento gaussiano |
| `GF_ADMIN_PASSWORD` | `admin` | Contraseña de Grafana |

---

## Instalación manual (alternativa)

Si prefieres instalar sin el script:

```powershell
python -m venv .venv
.venv\Scripts\pip install `
  -r services/api/requirements.txt `
  -r services/frontend/requirements.txt `
  -r services/seeder/requirements.txt `
  -r model/requirements.txt `
  -r tests/requirements.txt
.venv\Scripts\pip install "pathspec<0.12"
Copy-Item .env.example .env
.venv\Scripts\python model/train.py
```

---

## Dependencias principales

| Paquete | Versión | Uso |
|---|---|---|
| `fastapi` | 0.111.0 | Framework de la API REST |
| `uvicorn[standard]` | 0.29.0 | Servidor ASGI |
| `scikit-learn` | 1.4.2 | SGDClassifier, train_test_split, métricas |
| `dvc` | 3.51.2 | Versionado de artefactos ML |
| `dvc-s3` | 3.1.0 | Remote DVC compatible con S3/MinIO |
| `prometheus-client` | 0.20.0 | Emisión de métricas |
| `streamlit` | 1.35.0 | Frontend interactivo |
| `pandas` | 2.2.2 | Lectura de CSV en el frontend |
| `httpx` | 0.27.0 | Cliente HTTP async (wrapper + tests) |

---

## Remotes DVC

El proyecto tiene dos remotes configurados en `.dvc/config`:

| Remote | Tipo | URL | Cuándo usar |
|---|---|---|---|
| `local` | Directorio | `dvc-remote/` | Por defecto; no requiere Docker |
| `minio` | S3 | `s3://dvc-artifacts` en `:9000` | Requiere MinIO corriendo |

```powershell
# Usar el remote local (por defecto)
.\pipeline.ps1 train -Version v2.0.0 -RandomState 42

# Usar MinIO (requiere docker compose up minio)
.\pipeline.ps1 train -Version v2.1.0 -RandomState 7 -Remote minio
```

---

## Acceso a MinIO

| Recurso | URL | Credenciales |
|---|---|---|
| API S3 | http://localhost:9000 | `minioadmin` / `minioadmin` |
| Consola web | http://localhost:9001 | `minioadmin` / `minioadmin` |
| Bucket DVC | `dvc-artifacts` | auto-creado por `minio-init` |

---

## Permisos de ejecución de scripts en PowerShell

Si PowerShell bloquea la ejecución:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```
