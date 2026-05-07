# Testing

## Ejecutar los tests

La API debe estar corriendo antes de lanzar la suite.

```powershell
# Con el CLI (recomendado)
.\pipeline.ps1 test

# Directamente con pytest
.venv\Scripts\pytest tests/ -v --tb=short

# Contra una URL diferente
$env:API_URL = "http://staging:8000"
.venv\Scripts\pytest tests/
```

Los tests se **auto-omiten** (`pytest.skip`) si la API no está disponible, por lo que no fallan en entornos sin servidor.

---

## Suite de tests (52 tests)

| Archivo | Tests | Qué cubre |
|---|---|---|
| [test_health.py](../tests/test_health.py) | 4 | `/health` devuelve 200, `status=ok`, `model_loaded=True`, version string |
| [test_inference.py](../tests/test_inference.py) | 11 | Predicción binaria con 30 features, probabilidades suman 1, `request_id`, 4 entradas inválidas (422), 20 peticiones concurrentes |
| [test_training.py](../tests/test_training.py) | 12 | `partial_fit` con vectores de 30 features, `samples_trained`, versión actualizada, 5 entradas inválidas (422), drift score EMA |
| [test_versioning.py](../tests/test_versioning.py) | 7 | `/version/current`, consistencia con `/health`, ref inexistente (500), ref vacío (422) |
| [test_metrics.py](../tests/test_metrics.py) | 7 | Las 8 métricas presentes (incluye `pipeline_model_load_duration_seconds`), `model_loaded=1.0`, contadores incrementan, histograma de latencia |
| [test_flow.py](../tests/test_flow.py) | 8 | Golden path completo (health→infer→train→infer→drift→metrics→version), `request_id` propagation, 5 rondas de entrenamiento, acepta 1/5/30/60/100 features |

---

## Vector de features de referencia (`FEATURES_30`)

`tests/conftest.py` define el vector de referencia como la muestra #0 del dataset breast cancer (caso maligno, clase 0):

```python
FEATURES_30 = [
    # media (radius, texture, perimeter, area, smoothness, compactness, concavity, concpts, symmetry, fracdim)
    17.99, 10.38, 122.80, 1001.0, 0.1184, 0.2776, 0.3001, 0.1471, 0.2419, 0.0787,
    # error estándar
     1.095,  0.905,   8.589,  153.4, 0.0064, 0.0490, 0.0537, 0.0159, 0.0300, 0.0062,
    # peor valor
    25.38,  17.33,  184.60, 2019.0, 0.1622, 0.6656, 0.7119, 0.2654, 0.4601, 0.1189,
]
```

La predicción esperada es clase **0** (maligno) con alta probabilidad.

---

## Fixture principal

`tests/conftest.py` define un `httpx.Client` de alcance sesión:

```python
@pytest.fixture(scope="session")
def client(api_url: str) -> httpx.Client:
    with httpx.Client(base_url=api_url, timeout=15.0) as c:
        try:
            c.get("/health").raise_for_status()
        except Exception as exc:
            pytest.skip(f"API not available at {api_url} — {exc}")
        yield c
```

Un único cliente HTTP se comparte entre todos los tests. El estado del modelo (versión, pesos) se acumula a lo largo de la sesión — esto es intencionado: `test_flow.py` verifica que el estado es coherente entre operaciones consecutivas.

---

## Configuración (`pytest.ini`)

```ini
[pytest]
testpaths = tests
addopts   = -v --tb=short
```

---

## Instalar dependencias de test

```powershell
.venv\Scripts\pip install -r tests/requirements.txt
```

Dependencias: `pytest==8.2.0`, `httpx==0.27.0`.

---

## Añadir nuevos tests

1. Crea un archivo `tests/test_<funcionalidad>.py`
2. Usa el fixture `client: httpx.Client` para las llamadas HTTP
3. Añade datos de prueba al módulo o usa `FEATURES_30` de `conftest.py`
4. Para tests parametrizados: `@pytest.mark.parametrize`

Ejemplo:

```python
from conftest import FEATURES_30

def test_infer_returns_binary(client):
    body = client.post("/infer/", json={"features": FEATURES_30}).json()
    assert body["prediction"] in (0, 1)
    assert body["prediction"] == 0  # muestra maligna conocida
```

---

## Tests de drift

`test_training.py` incluye dos tests específicos de drift:

```python
def test_drift_score_emitted_after_two_batches(client):
    # Dos batches son suficientes para inicializar la referencia EMA y emitir scores
    ...

def test_drift_score_high_when_distribution_shifts(client):
    # Un batch muy alejado de la distribución normal debe producir score > 0
    # (features = [100.0]*30 frente a referencia de breast cancer ≈ [14, 19, 91, ...])
    ...
```
