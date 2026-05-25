# Dataset: Breast Cancer Wisconsin

| Propiedad | Valor |
|---|---|
| Fuente | `sklearn.datasets.load_breast_cancer()` |
| Muestras | 569 (212 malignas 37.3 %, 357 benignas 62.7 %) |
| Features | 30 (reales, positivas, sin valores faltantes) |
| Clases | 0 = maligno · 1 = benigno |
| Tarea | Clasificación binaria supervisada |

---

## Features (30 atributos)

10 propiedades × 3 estadísticos (_mean, _se, _worst) = 30 features:

| Propiedad base | _mean (idx 0-9) | _se (idx 10-19) | _worst (idx 20-29) |
|---|---|---|---|
| radius | 0 | 10 | 20 |
| texture | 1 | 11 | 21 |
| perimeter | 2 | 12 | 22 |
| area | 3 | 13 | 23 |
| smoothness | 4 | 14 | 24 |
| compactness | 5 | 15 | 25 |
| concavity | 6 | 16 | 26 |
| concpts | 7 | 17 | 27 |
| symmetry | 8 | 18 | 28 |
| fracdim | 9 | 19 | 29 |

Nombres completos: `radius_mean` … `fracdim_mean`, `radius_se` … `fracdim_se`, `radius_worst` … `fracdim_worst`.

---

## Muestra #0 (maligna, clase 0)

```json
{
  "features": [
    17.99, 10.38, 122.80, 1001.0, 0.1184, 0.2776, 0.3001, 0.1471, 0.2419, 0.0787,
     1.095,  0.905,   8.589,  153.4, 0.0064, 0.0490, 0.0537, 0.0159, 0.0300, 0.0062,
    25.38,  17.33,  184.60, 2019.0, 0.1622, 0.6656, 0.7119, 0.2654, 0.4601, 0.1189
  ]
}
```

Predicción esperada: `prediction: 0` (maligno).

---

## Modelo: SGDClassifier

| Hiperparámetro | Valor |
|---|---|
| `loss` | `"log_loss"` — produce `predict_proba` calibradas |
| `max_iter` | 1000 |
| `random_state` | 42 (configurable) |

**Métricas (split 80/20 estratificado):**

| Métrica | Valor |
|---|---|
| Accuracy | 0.833 |
| F1-score (benigno) | 0.857 |
| Precision | 0.934 |
| Recall | 0.792 |

SGD es apropiado por soporte nativo de `partial_fit` (aprendizaje incremental sin re-leer el dataset) y bajo coste computacional en tiempo real.

---

## Drift simulado

El seeder genera vectores con desplazamiento `+ DRIFT_MAGNITUDE * σ_feature` tras `DRIFT_ONSET_AFTER_S` segundos. `DriftTracker` (EMA α = 0.05) emite `pipeline_data_drift_score{feature=<nombre>}` para las 30 dimensiones. Las features con mayor poder discriminativo (`radius_mean`, `area_mean`, `concavity_worst`) son las más sensibles.
