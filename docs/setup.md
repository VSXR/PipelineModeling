# Setup

## Prerrequisitos

| Herramienta | Versión mínima | Verificar |
|---|---|---|
| Python | 3.11 | `python --version` |
| Git | 2.x | `git --version` |
| Docker Desktop | 4.x | `docker compose version` |

> Docker solo es necesario para Prometheus y Grafana. La API, el frontend y el seeder corren en local.

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
5. Entrena `model/weights/model.pkl` si no existe

---

## Variables de entorno

Todas están en `.env` (generado desde `.env.example`). Las más relevantes:

| Variable | Por defecto | Descripción |
|---|---|---|
| `MODEL_PATH` | ruta local al `.pkl` | Ruta del artefacto del modelo |
| `GIT_REPO_PATH` | raíz del repo | Usado por DVC para `git checkout` |
| `DVC_REMOTE_PATH` | `./dvc-remote` | Remote local de DVC |
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

## Permisos de ejecución de scripts en PowerShell

Si PowerShell bloquea la ejecución:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```
