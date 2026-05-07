# PipelineModeling

Sistema de aprendizaje continuo para modelos de IA orquestado con Docker Compose. Integra inferencia en tiempo real, reentrenamiento incremental (`partial_fit`), control de versiones de artefactos con DVC + Git, simulación de tráfico y drift, y monitorización con Prometheus y Grafana.

---

## Arquitectura

```
┌──────────────────────────────────────────────────────────────────┐
│                        pipeline_net (bridge)                     │
│                                                                  │
│  ┌──────────┐   HTTP    ┌─────────────────┐   scrape   ┌──────┐ │
│  │ frontend │──────────▶│   api (FastAPI)  │◀──────────│ prom │ │
│  │:8501     │           │   :8000         │            │:9090 │ │
│  └──────────┘           │  /infer/        │            └──────┘ │
│                         │  /train/        │               │     │
│  ┌──────────┐   HTTP    │  /version/      │            ┌──────┐ │
│  │  seeder  │──────────▶│  /health        │            │grafana│ │
│  │(async)   │           │  /metrics       │            │:3000 │ │
│  └──────────┘           └────────┬────────┘            └──────┘ │
│                                  │ DVC pull                      │
│                         ┌────────▼────────┐                      │
│                         │  dvc-remote/    │ (bind mount)         │
│                         │  model_weights  │ (named volume)       │
│                         └─────────────────┘                      │
└──────────────────────────────────────────────────────────────────┘
```

| Servicio | Puerto | Descripción |
|---|---|---|
| API (FastAPI) | `8000` | Inferencia, entrenamiento incremental, gestión de versiones |
| Frontend (Streamlit) | `8501` | Panel de control visual |
| Prometheus | `9090` | Ingesta de métricas |
| Grafana | `3000` | Dashboards (user: `admin`, pass: ver `.env`) |
| Seeder | — | Generador de tráfico sintético y drift |

---

## Estructura del proyecto

```
PipelineModeling/
├── start.ps1                         # Arranca todo el workspace con un comando
├── stop.ps1                          # Para todos los servicios
├── docker-compose.yml
├── docker-compose.override.yml       # Override local: Prometheus apunta a host.docker.internal
├── dvc.yaml                          # Pipeline DVC: train → model.pkl
├── dvc.lock                          # Generado tras dvc repro (rastreado por git)
├── .dvc/config                       # Remote local → ./dvc-remote
├── .env.example
├── dvc-remote/                       # Remote DVC local (bind-mount; en .gitignore)
├── model/
│   ├── train.py                      # Script de entrenamiento inicial
│   ├── requirements.txt
│   ├── metrics.json                  # Salida de métricas DVC
│   └── weights/
│       └── model.pkl                 # Artefacto gestionado por DVC (no en git)
├── services/
│   ├── api/
│   │   ├── Dockerfile                # Multi-stage; contexto = repo root
│   │   ├── main.py                   # App FastAPI + Instrumentator + lifespan
│   │   ├── requirements.txt
│   │   ├── core/
│   │   │   ├── config.py             # Pydantic Settings
│   │   │   ├── metrics.py            # Gauges, Counters, Histogramas Prometheus
│   │   │   └── model_manager.py      # Singleton; asyncio locks; DVC pull
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── inference.py          # POST /infer/
│   │   │   ├── training.py           # POST /train/ + detección de drift (EMA)
│   │   │   └── versioning.py         # GET /version/current · POST /version/switch
│   │   └── schemas/
│   │       ├── __init__.py           # Re-exporta todos los modelos
│   │       ├── inference.py          # InferenceRequest / InferenceResponse
│   │       ├── training.py           # TrainingRequest / TrainingResponse
│   │       └── versioning.py         # VersionSwitch*, VersionCurrentResponse
│   ├── seeder/
│   │   ├── seeder.py                 # 3 corutinas: inference, training, drift
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   ├── wrapper/
│   │   ├── client.py                 # PipelineClient (async context manager)
│   │   └── requirements.txt
│   └── frontend/
│       ├── app.py                    # Streamlit: status, infer, train, versioning
│       ├── requirements.txt
│       └── Dockerfile
└── monitoring/
    ├── prometheus/
    │   ├── prometheus.yml
    │   └── alerts.yml
    └── grafana/provisioning/
        ├── dashboards/pipeline.json
        └── datasources/datasource.yml
```

---

## Prerrequisitos

- **Docker Desktop** ≥ 4.x (incluye Compose v2)
- **Git** ≥ 2.x
- **Python 3.11+** con entorno virtual `.venv` configurado (ver abajo)

Para verificar:

```powershell
docker compose version   # debe mostrar v2.x
git --version
python --version
```

### Configurar el entorno virtual (primera vez)

```powershell
python -m venv .venv
.venv\Scripts\pip install `
  -r services/api/requirements.txt `
  -r services/frontend/requirements.txt `
  -r services/seeder/requirements.txt `
  -r model/requirements.txt
```

---

## Inicio rápido

Hay dos modos de arranque. Elige según tu caso de uso:

| Modo | Cuándo usarlo | Comando |
|---|---|---|
| **Script local** (recomendado para desarrollo) | API, frontend y seeder corren en `.venv` con `--reload`; Prometheus y Grafana en Docker | `.\start.ps1` |
| **Docker Compose completo** | Todo en contenedores; ideal para pruebas de integración o entrega | `docker compose up --build` |

---

### Modo A — Script local (`start.ps1`)

#### 1. Clonar el repositorio

```powershell
git clone <url-del-repositorio>
cd PipelineModeling
```

#### 2. Ejecutar el script de arranque

```powershell
.\start.ps1
```

> **Primera vez:** si PowerShell bloquea la ejecución, habilita scripts de usuario:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

El script realiza automáticamente:

1. Verifica que Docker Desktop esté corriendo y que `.venv` exista
2. Detecta conflictos de puertos (8000, 8501, 9090, 3000) y advierte antes de continuar
3. Crea `.env` desde `.env.example` si no existe
4. Entrena el modelo inicial si `model/weights/model.pkl` no existe
5. Levanta **Prometheus** y **Grafana** en Docker (`docker-compose.override.yml` activo)
6. Abre una ventana de terminal para la **API** (uvicorn `--reload`)
7. Espera a que la API pase el healthcheck (hasta 60 s)
8. Abre una ventana de terminal para el **Frontend** (Streamlit)
9. Abre una ventana de terminal para el **Seeder**
10. Muestra la tabla de URLs

Al terminar tienes **3 ventanas de terminal** abiertas (API, Frontend, Seeder) donde puedes ver los logs en tiempo real.

#### 3. Acceder a los servicios

| URL | Servicio |
|---|---|
| http://localhost:8501 | Frontend (panel de control) |
| http://localhost:8000/docs | API — Swagger UI interactivo |
| http://localhost:8000/health | Estado de la API en JSON |
| http://localhost:9090 | Prometheus |
| http://localhost:3000 | Grafana (admin / ver `.env`) |

#### 4. Apagar

```powershell
.\stop.ps1
```

Cierra las tres ventanas de terminal, para los contenedores de Prometheus y Grafana, y elimina `.pids.json`.

---

### Modo B — Docker Compose completo

#### 1. Clonar y configurar

```powershell
git clone <url-del-repositorio>
cd PipelineModeling
Copy-Item .env.example .env
```

#### 2. Construir e iniciar

```powershell
docker compose up --build
```

El flag `--build` es necesario en el primer arranque o cuando se modifica código. Para arranques posteriores:

```powershell
docker compose up
```

#### 3. Verificar el estado

```powershell
docker compose ps
```

Todos los servicios deben mostrar `healthy` o `running`.

#### 4. Apagar

```powershell
docker compose down       # preserva volúmenes
docker compose down -v    # elimina también los volúmenes
```

---

## Uso del sistema

### Panel de control (Frontend)

Abre http://localhost:8501. El panel tiene cuatro secciones:

- **System Status** — estado del healthcheck, versión activa del modelo y enlace directo a Grafana
- **Manual Inference** — introduce valores para los 10 features (`f0`–`f9`) y obtén una predicción con probabilidad
- **Trigger Training** — genera un batch sintético de tamaño configurable y ejecuta `partial_fit`
- **Model Version Control** — introduce un git ref (tag, rama o SHA) para hacer un hot-swap del modelo via DVC

### API directa (Swagger)

Abre http://localhost:8000/docs para explorar y ejecutar cualquier endpoint desde el navegador.

### Seeder automático

En cuanto arranca, el seeder envía peticiones de inferencia al ritmo configurado (por defecto 20 req/s). A los 120 segundos activa una deriva estadística (`DRIFT_MAGNITUDE=2.0`) que desplaza la distribución de features, provocando que los scores de drift de Prometheus superen el umbral de alerta (> 0.5). Esto es visible en Grafana en tiempo real.

---

## Flujo de versionado de modelos con DVC

Este flujo es necesario para usar el endpoint `/version/switch`. Si solo necesitas inferencia y entrenamiento continuo, puedes omitirlo.

### Prerrequisitos del flujo DVC

Instala las dependencias en el host:

```bash
pip install -r model/requirements.txt
pip install dvc==3.51.2
```

### Paso 1 — Entrenamiento inicial

```bash
python model/train.py
```

Esto genera `model/weights/model.pkl`, `model/metrics.json` y `model/plots/confusion_matrix.csv`.

### Paso 2 — Registrar el artefacto en DVC y ejecutar el pipeline

```bash
dvc repro
```

Este comando ejecuta el stage `train` definido en `dvc.yaml`, genera `dvc.lock` y actualiza el caché local de DVC en `.dvc/cache/`.

### Paso 3 — Publicar al remote local

```bash
dvc push
```

Copia los artefactos del caché DVC al directorio `./dvc-remote/`, que está bind-montado dentro del contenedor de la API en `/app/dvc-remote`. Cualquier push desde el host es inmediatamente accesible para la API.

### Paso 4 — Crear una versión Git

```bash
git add dvc.lock model/metrics.json model/plots/
git commit -m "feat: train model v1.0.0"
git tag v1.0.0
```

### Paso 5 — Entrenar una segunda versión (ejemplo de drift)

Modifica los parámetros en `model/train.py` (por ejemplo, incrementa `N_SAMPLES`) y repite los pasos 2–4 con un nuevo tag (`v1.1.0`).

### Paso 6 — Cambiar de versión en caliente desde el Frontend o la API

**Via Frontend** (http://localhost:8501): En la sección "Model Version Control", escribe `v1.0.0` y pulsa "Switch Version".

**Via API**:

```bash
curl -X POST http://localhost:8000/version/switch \
     -H "Content-Type: application/json" \
     -d '{"git_ref": "v1.0.0"}'
```

**Via wrapper de Python**:

```python
import asyncio
from services.wrapper.client import PipelineClient

async def main():
    async with PipelineClient("http://localhost:8000") as c:
        result = await c.switch_version("v1.0.0")
        print(result)

asyncio.run(main())
```

La API ejecuta `git checkout v1.0.0 -- .dvc` y `git checkout v1.0.0 -- dvc.lock` dentro del contenedor (usando el bind mount de `.git`), seguido de `dvc pull --force --remote local`. El modelo se recarga en caliente sin reiniciar el contenedor.

---

## Variables de entorno

Todas están documentadas en `.env.example`. Las más relevantes:

| Variable | Por defecto | Descripción |
|---|---|---|
| `MODEL_PATH` | `/app/model/weights/model.pkl` | Ruta interna del artefacto del modelo |
| `GIT_REPO_PATH` | `/app` | Directorio raíz del repo dentro del contenedor |
| `DVC_REMOTE_PATH` | `/app/dvc-remote` | Path del remote DVC dentro del contenedor |
| `REQUESTS_PER_SECOND` | `20` | Tasa de inferencia del seeder |
| `INFERENCE_CONCURRENCY` | `10` | Máximo de peticiones HTTP en vuelo simultáneas |
| `TRAINING_INTERVAL_S` | `30` | Segundos entre batches de entrenamiento del seeder |
| `TRAINING_BATCH_SIZE` | `50` | Muestras por batch de entrenamiento |
| `DRIFT_ONSET_AFTER_S` | `120` | Segundos hasta que el seeder activa la deriva de datos |
| `DRIFT_MAGNITUDE` | `2.0` | Magnitud del desplazamiento gaussiano de la deriva |
| `GF_ADMIN_PASSWORD` | `admin` | Contraseña del administrador de Grafana |

---

## Referencia de la API

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/health` | Estado del servicio y versión activa del modelo |
| `POST` | `/infer/` | Predicción sobre un vector de features |
| `POST` | `/train/` | Reentrenamiento incremental con `partial_fit` |
| `GET` | `/version/current` | Versión y estado de carga del modelo actual |
| `POST` | `/version/switch` | Hot-swap del modelo a un git ref via DVC |
| `GET` | `/metrics` | Métricas en formato Prometheus text |
| `GET` | `/docs` | Swagger UI |

Ejemplo de inferencia:

```bash
curl -X POST http://localhost:8000/infer/ \
     -H "Content-Type: application/json" \
     -d '{"features": [0.1, -0.2, 0.5, 1.0, -0.3, 0.8, 0.0, -1.2, 0.4, 0.7]}'
```

Ejemplo de entrenamiento:

```bash
curl -X POST http://localhost:8000/train/ \
     -H "Content-Type: application/json" \
     -d '{"features": [[0.1, -0.2, 0.5, 1.0, -0.3, 0.8, 0.0, -1.2, 0.4, 0.7]], "labels": [1]}'
```

---

## Monitorización

### Grafana

Accede a http://localhost:3000 (admin / contraseña en `.env`). El dashboard **PipelineModeling** se provisiona automáticamente e incluye:

- Inference RPS y latencia (p50, p95, p99)
- Tasa de errores de inferencia
- Muestras de entrenamiento acumuladas
- Estado de carga del modelo
- Score de drift por feature (`f0`–`f9`)

### Prometheus

Las métricas están disponibles en http://localhost:9090. Las alertas configuradas en `monitoring/prometheus/alerts.yml` son:

| Alerta | Condición | Severidad |
|---|---|---|
| `ModelNotLoaded` | `pipeline_model_loaded == 0` por > 1 min | critical |
| `HighInferenceErrorRate` | Tasa de errores > 5% en 5 min | warning |
| `HighInferenceLatencyP99` | p99 > 500 ms en 3 min | warning |
| `DataDriftDetected` | `pipeline_data_drift_score > 0.5` en 5 min | warning |

---

## Desarrollo y testing

### Arranque y parada con los scripts

```powershell
.\start.ps1   # arranca todo (verifica prerrequisitos, healthchecks, abre terminales)
.\stop.ps1    # para todo (PIDs + ventanas huérfanas + Docker)
```

`start.ps1` guarda los PIDs de los procesos locales en `.pids.json` (ignorado por git). Si hay puertos en uso, pregunta antes de continuar.

### Iterar sobre el código de la API

Con `.\start.ps1` activo, uvicorn corre con `--reload`. Cualquier cambio en `services/api/` se recarga automáticamente sin reiniciar el resto del stack.

### Reconstruir un servicio Docker específico

```powershell
docker compose up --build api --no-deps
```

### Ver logs en tiempo real (modo Docker Compose)

```powershell
docker compose logs -f api seeder        # API y seeder
docker compose logs -f                   # todos los servicios
```

### Forzar un evento de drift manualmente

El seeder activa el drift automáticamente tras `DRIFT_ONSET_AFTER_S` segundos. Para forzarlo inmediatamente en modo local, cierra la ventana del seeder y ábrela de nuevo con la variable a 0:

```powershell
# En una terminal nueva:
$env:API_URL            = "http://localhost:8000"
$env:DRIFT_ONSET_AFTER_S = "0"
$env:DRIFT_MAGNITUDE    = "2.0"
& .venv\Scripts\python.exe services\seeder\seeder.py
```

En modo Docker Compose:

```powershell
docker compose stop seeder
$env:DRIFT_ONSET_AFTER_S = "0"
docker compose up -d seeder
```

### Tests automatizados

El proyecto incluye una suite de integración de **52 tests** que ejercita el pipeline completo contra la API en ejecución. Los tests usan `pytest` + `httpx` y se auto-omiten (`pytest.skip`) si la API no está disponible.

#### Instalación de dependencias de test

```powershell
.venv\Scripts\pip install -r tests/requirements.txt
```

#### Ejecutar los tests

La API debe estar corriendo (`.\start.ps1` o `docker compose up`) antes de lanzar la suite.

```powershell
# Contra la API local (por defecto http://localhost:8000)
.venv\Scripts\pytest tests/

# Contra otra URL (por ejemplo, un entorno de staging)
$env:API_URL = "http://staging:8000"
.venv\Scripts\pytest tests/
```

Para ver el resumen sin el detalle de cada test:

```powershell
.venv\Scripts\pytest tests/ -q
```

#### Estructura de la suite

| Archivo | Tests | Qué cubre |
|---|---|---|
| [tests/test_health.py](tests/test_health.py) | 4 | `/health` devuelve 200, status ok, model_loaded, version string |
| [tests/test_inference.py](tests/test_inference.py) | 11 | Predicción binaria, probabilidades, `request_id`, entradas inválidas (422), 20 peticiones concurrentes |
| [tests/test_training.py](tests/test_training.py) | 12 | `partial_fit`, samples_trained, versión actualizada, entradas inválidas (422), drift score |
| [tests/test_versioning.py](tests/test_versioning.py) | 7 | `/version/current`, consistencia con `/health`, ref inexistente (500), ref vacío (422) |
| [tests/test_metrics.py](tests/test_metrics.py) | 7 | Todas las métricas presentes, `model_loaded=1.0`, contadores incrementan, histograma de latencia |
| [tests/test_flow.py](tests/test_flow.py) | 8 | Golden path completo (health→infer→train→infer→drift→metrics→version), propagación de `request_id`, 5 rondas de entrenamiento consecutivas |

El fixture `client` en [tests/conftest.py](tests/conftest.py) es de alcance sesión: crea un único `httpx.Client` para todos los tests y lo reutiliza, por lo que el orden de ejecución importa en los tests de flujo (el estado del modelo se acumula entre llamadas).

#### Configuración (`pytest.ini`)

```ini
[pytest]
testpaths = tests
addopts = -v --tb=short
```

La variable de entorno `API_URL` sobreescribe la URL base del cliente (por defecto `http://localhost:8000`).

---

## Solución de problemas

**`start.ps1` falla con "running scripts is disabled"**

- Ejecuta una vez: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

**`start.ps1` falla con "Docker Desktop is not running"**

- Abre Docker Desktop y espera a que el icono de la barra de tareas deje de girar antes de relanzar el script.

**`start.ps1` falla con "API did not become healthy within 60s"**

- Mira la ventana de terminal de la API para ver el error. Las causas más frecuentes son un puerto 8000 ocupado por otro proceso o un import error en el código.

**`stop.ps1` no cierra una ventana de terminal**

- Ciérrala manualmente. `stop.ps1` es best-effort: si el PID ya no existe o el proceso cambió, lo ignora.

**El contenedor `api` no pasa el healthcheck**

- Revisa los logs: `docker compose logs api`
- Causa más frecuente: el modelo no se pudo cargar. Si `model/weights/model.pkl` no existe en el volumen, la API crea un `SGDClassifier` vacío, lo que es correcto. El healthcheck fallará solo si hay una excepción en el arranque.

**`/version/switch` devuelve 500 con error de git**

- El bind mount `.git` requiere que el repositorio esté inicializado. Verifica: `git log --oneline -3`.
- El ref introducido debe existir en el repositorio local (tags o ramas locales). Para refs remotos, ejecuta primero `git fetch` en el host.

**`dvc pull` falla con "file not found in remote"**

- El modelo no ha sido pusheado al remote local. Ejecuta `dvc repro && dvc push` en el host.
- Verifica que el directorio `./dvc-remote/` contiene archivos: `ls dvc-remote/`.

**El seeder no arranca**

- El seeder espera a que `/health` de la API devuelva `model_loaded: true`. Si la API tarda más de 150 s (30 intentos × 5 s), el seeder arranca de todas formas. Revisa: `docker compose logs seeder`.

**Grafana muestra "No data"**

- Prometheus necesita haber recibido al menos un scrape. Espera 15–20 s tras el arranque.
- Verifica que Prometheus alcanza la API: http://localhost:9090/targets debe mostrar `pipeline_api` en estado `UP`.

**Errores de permisos en el volumen `model_weights`**

- Si el volumen fue creado con otro usuario, elimínalo y recréalo: `docker compose down -v && docker compose up`.
