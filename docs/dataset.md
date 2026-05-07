# Dataset: Breast Cancer Wisconsin (Diagnostic)

## Descripción general

| Atributo | Valor |
|---|---|
| **Nombre** | Breast Cancer Wisconsin (Diagnostic) |
| **Fuente** | UCI Machine Learning Repository / scikit-learn built-in |
| **Carga** | `sklearn.datasets.load_breast_cancer()` |
| **Publicado** | 1992, Universidad de Wisconsin-Madison |
| **Autores** | W.H. Wolberg, W.N. Street, O.L. Mangasarian |

El dataset registra características de núcleos celulares obtenidas a partir de imágenes digitalizadas de aspiración con aguja fina (FNA) de masas mamarias. El objetivo es distinguir entre tumores **malignos** (clase 0) y **benignos** (clase 1).

---

## Estadísticas del dataset

| Propiedad | Valor |
|---|---|
| Muestras totales | 569 |
| Muestras malignas (clase 0) | 212 (37.3 %) |
| Muestras benignas (clase 1) | 357 (62.7 %) |
| Features | 30 (reales, todas positivas) |
| Valores faltantes | Ninguno |
| Tipo de tarea | Clasificación binaria supervisada |

---

## Features (30 atributos)

Para cada núcleo celular se calculan 10 propiedades geométricas y texturales. Cada propiedad se registra en tres estadísticos distintos: **media** (_mean), **error estándar** (_se) y **peor valor** (_worst = media de los 3 mayores valores). Esto produce 10 × 3 = 30 features.

### Las 10 propiedades base

| # | Nombre | Descripción |
|---|---|---|
| 1 | `radius` | Radio medio de los núcleos |
| 2 | `texture` | Desviación estándar de los valores de gris |
| 3 | `perimeter` | Perímetro del núcleo |
| 4 | `area` | Área del núcleo |
| 5 | `smoothness` | Variación local en las longitudes de radio |
| 6 | `compactness` | (perímetro² / área) – 1.0 |
| 7 | `concavity` | Severidad de las porciones cóncavas del contorno |
| 8 | `concave_points` | Número de porciones cóncavas del contorno |
| 9 | `symmetry` | Simetría del núcleo |
| 10 | `fractal_dimension` | "Aproximación de la costa" – 1 |

### Tabla completa de los 30 features del modelo

| Índice | Nombre en el modelo | Descripción |
|---|---|---|
| 0 | `radius_mean` | Radio (media) |
| 1 | `texture_mean` | Textura (media) |
| 2 | `perimeter_mean` | Perímetro (media) |
| 3 | `area_mean` | Área (media) |
| 4 | `smoothness_mean` | Suavidad (media) |
| 5 | `compactness_mean` | Compacidad (media) |
| 6 | `concavity_mean` | Concavidad (media) |
| 7 | `concpts_mean` | Puntos cóncavos (media) |
| 8 | `symmetry_mean` | Simetría (media) |
| 9 | `fracdim_mean` | Dimensión fractal (media) |
| 10 | `radius_se` | Radio (error estándar) |
| 11 | `texture_se` | Textura (error estándar) |
| 12 | `perimeter_se` | Perímetro (error estándar) |
| 13 | `area_se` | Área (error estándar) |
| 14 | `smoothness_se` | Suavidad (error estándar) |
| 15 | `compactness_se` | Compacidad (error estándar) |
| 16 | `concavity_se` | Concavidad (error estándar) |
| 17 | `concpts_se` | Puntos cóncavos (error estándar) |
| 18 | `symmetry_se` | Simetría (error estándar) |
| 19 | `fracdim_se` | Dimensión fractal (error estándar) |
| 20 | `radius_worst` | Radio (peor = media de los 3 mayores) |
| 21 | `texture_worst` | Textura (peor) |
| 22 | `perimeter_worst` | Perímetro (peor) |
| 23 | `area_worst` | Área (peor) |
| 24 | `smoothness_worst` | Suavidad (peor) |
| 25 | `compactness_worst` | Compacidad (peor) |
| 26 | `concavity_worst` | Concavidad (peor) |
| 27 | `concpts_worst` | Puntos cóncavos (peor) |
| 28 | `symmetry_worst` | Simetría (peor) |
| 29 | `fracdim_worst` | Dimensión fractal (peor) |

---

## Ejemplo de muestra

Muestra #0 del dataset (maligna, clase 0):

```json
{
  "features": [
    17.99, 10.38, 122.80, 1001.0, 0.1184, 0.2776, 0.3001, 0.1471, 0.2419, 0.0787,
     1.095,  0.905,   8.589,  153.4, 0.0064, 0.0490, 0.0537, 0.0159, 0.0300, 0.0062,
    25.38,  17.33,  184.60, 2019.0, 0.1622, 0.6656, 0.7119, 0.2654, 0.4601, 0.1189
  ]
}
```

Predicción esperada: `prediction: 0` (maligno), con alta confianza.

---

## Modelo: SGDClassifier

El modelo de clasificación usa **Stochastic Gradient Descent** (SGD) con función de pérdida log-loss (regresión logística online):

| Hiperparámetro | Valor | Justificación |
|---|---|---|
| `loss` | `"log_loss"` | Produce probabilidades calibradas, necesario para `/infer/` |
| `max_iter` | 1000 | Suficiente para convergencia en 569 muestras |
| `random_state` | 42 (configurable) | Reproducibilidad del split y del SGD |

### Métricas de evaluación (split 80/20 estratificado)

| Métrica | Valor |
|---|---|
| **Accuracy** | 0.83333 |
| **F1-score** (clase 1 = benigno) | 0.85714 |
| **Precision** | 0.93443 |
| **Recall** | 0.79167 |
| Muestras de test | 114 |

Las métricas se guardan en `model/metrics.json` y son rastreadas por DVC en cada versión.

### Por qué SGD es apropiado para este pipeline

1. **Soporte nativo de `partial_fit`** — permite reentrenamiento incremental sin re-leer todo el dataset histórico.
2. **Eficiencia en memoria** — procesa una muestra o un mini-batch a la vez; escala a flujos de datos en tiempo real.
3. **Probabilidades calibradas** — `loss="log_loss"` produce `predict_proba` utilizable para clasificación y alertas de drift.
4. **Abstracción `BasePredictor`** — el modelo concreto puede reemplazarse (XGBoost online, HuggingFace, ONNX) sin tocar la API.

---

## Consideraciones éticas y limitaciones

| Aspecto | Detalle |
|---|---|
| **Dominio** | Datos clínicos de diagnóstico oncológico |
| **Uso en este proyecto** | Académico/educativo; **no apto para decisiones médicas reales** |
| **Desbalance de clases** | 37 % maligno / 63 % benigno — el modelo tiende a priorizar benignos |
| **Distribución de features** | Escalas muy dispares (area ∈ [0,2500], fracdim ∈ [0,0.3]) — el seeder simula drift en esta distribución |
| **Generalización** | El modelo se reentrena con `partial_fit` en producción; la métrica de drift detecta cuando la distribución de inferencia se aleja del entrenamiento |

---

## Cómo se genera el drift simulado

El **Seeder** genera distribuciones de entrada que derivan del dataset real:

1. **Fase normal** (primeros `DRIFT_ONSET_AFTER_S` segundos): muestras del dataset con ruido gaussiano pequeño.
2. **Fase de drift**: desplazamiento gradual de la media de cada feature en `DRIFT_MAGNITUDE` desviaciones estándar.

El `DriftTracker` (EMA, α = 0.05) detecta este desplazamiento y emite `pipeline_data_drift_score{feature=<nombre>}` para cada una de las 30 features.

---

## Referencias

- Wolberg, W.H., Street, W.N., & Mangasarian, O.L. (1992). *Breast Cancer Wisconsin (Diagnostic) Data Set*. UCI Machine Learning Repository.
- Mangasarian, O.L. & Wolberg, W.H. (1990). *Cancer diagnosis via linear programming*. SIAM News, 23(5), 1–18.
- scikit-learn documentation: [sklearn.datasets.load_breast_cancer](https://scikit-learn.org/stable/modules/generated/sklearn.datasets.load_breast_cancer.html)
