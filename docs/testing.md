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
| [test_inference.py](../tests/test_inference.py) | 11 | Predicción binaria, probabilidades suman 1, `request_id`, 4 entradas inválidas (422), 20 peticiones concurrentes |
| [test_training.py](../tests/test_training.py) | 12 | `partial_fit`, `samples_trained`, versión actualizada tras entrenamiento, 5 entradas inválidas (422), drift score |
| [test_versioning.py](../tests/test_versioning.py) | 7 | `/version/current`, consistencia con `/health`, ref inexistente (500), ref vacío (422) |
| [test_metrics.py](../tests/test_metrics.py) | 7 | Las 7 métricas presentes, `model_loaded=1.0`, contadores incrementan, histograma de latencia |
| [test_flow.py](../tests/test_flow.py) | 8 | Golden path completo (health→infer→train→infer→drift→metrics→version), `request_id` propagation, 5 rondas de entrenamiento |

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
3. Añade datos de prueba al módulo o usa `FEATURES_10` de `conftest.py`
4. Para tests parametrizados: `@pytest.mark.parametrize`

Ejemplo:

```python
from conftest import FEATURES_10

def test_infer_returns_binary(client):
    body = client.post("/infer/", json={"features": FEATURES_10}).json()
    assert body["prediction"] in (0, 1)
```
