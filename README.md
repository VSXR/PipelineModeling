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
├── docker-compose.yml
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
│   │   │   ├── inference.py          # POST /infer/
│   │   │   ├── training.py           # POST /train/ + detección de drift (EMA)
│   │   │   └── versioning.py         # GET /version/current · POST /version/switch
│   │   └── shemas/
│   │       └── payloads.py           # Modelos Pydantic v2 request/response
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

- **Docker Desktop** ≥ 4.x (incluye Compose v2) o Docker Engine + `docker compose` plugin
- **Git** ≥ 2.x
- **Python 3.11+** (solo para el flujo de DVC en el host; no necesario para el arranque básico)

Para verificar:

```bash
docker compose version   # debe mostrar v2.x
git --version
python --version
```

---

## Inicio rápido

### 1. Clonar y configurar el entorno

```bash
git clone <url-del-repositorio>
cd PipelineModeling
cp .env.example .env
```

Edita `.env` si necesitas cambiar la contraseña de Grafana u otros parámetros. Los valores por defecto son suficientes para desarrollo local.

### 2. Construir e iniciar todos los servicios

```bash
docker compose up --build
```

El flag `--build` es necesario en el primer arranque o cuando se modifica código. Para arranques posteriores:

```bash
docker compose up
```

Docker Compose respeta el orden de dependencias. El seeder y el frontend esperan a que el healthcheck de la API pase antes de arrancar.

### 3. Verificar el estado

```bash
docker compose ps
```

Todos los servicios deben mostrar `healthy` o `running`. Si alguno aparece como `restarting`, consulta la sección [Solución de problemas](#solución-de-problemas).

### 4. Acceder a los servicios

| URL | Servicio |
|---|---|
| http://localhost:8501 | Frontend (panel de control) |
| http://localhost:8000/docs | API — Swagger UI interactivo |
| http://localhost:8000/health | Estado de la API en JSON |
| http://localhost:9090 | Prometheus |
| http://localhost:3000 | Grafana (admin / admin) |

### 5. Apagar

```bash
docker compose down          # detiene y elimina los contenedores, preserva volúmenes
docker compose down -v       # también elimina los volúmenes (datos persistentes)
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

### Ejecutar solo la API en local (sin Docker)

```bash
cd services/api
pip install -r requirements.txt
MODEL_PATH=../../model/weights/model.pkl \
GIT_REPO_PATH=../.. \
uvicorn main:app --reload --port 8000
```

### Reconstruir un servicio específico sin reiniciar el stack

```bash
docker compose up --build api --no-deps
```

### Ver logs en tiempo real

```bash
docker compose logs -f api seeder        # API y seeder
docker compose logs -f                   # todos los servicios
```

### Forzar un evento de drift manualmente

El seeder activa el drift de forma automática tras `DRIFT_ONSET_AFTER_S` segundos. Para forzarlo inmediatamente, reinicia el seeder con un onset de 0:

```bash
docker compose stop seeder
DRIFT_ONSET_AFTER_S=0 docker compose up -d seeder
```

---

## Solución de problemas

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
