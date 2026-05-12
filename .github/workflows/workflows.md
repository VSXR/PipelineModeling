# Documentación de GitHub Actions Workflows

Este directorio contiene las definiciones de los flujos de trabajo automatizados para la Integración Continua (CI), el Entrenamiento Continuo (CT) y el Despliegue Continuo (CD) del proyecto PipelineModeling.

## Estructura de la Automatización

El ciclo de vida del software está dividido en tres etapas principales que aseguran la calidad del código, la precisión del modelo y la estabilidad del despliegue.

---

## 1. Integración Continua (CI) - `ci.yml`

**Propósito:** Validar la integridad del código fuente de la API mediante la ejecución de pruebas unitarias automáticas en cada cambio.

- **Activación (Triggers):**
  - Cada `push` en las ramas `master` o `develop`.
  - Cada `pull_request` dirigido a la rama `master`.
- **Trabajos (Jobs):**
  - `unit-tests`: Configura un entorno Python 3.11, instala las dependencias de la API y los tests, y ejecuta `pytest`. Se omiten los tests de integración de infraestructura para mantener la rapidez del flujo.
- **Cache:** Utiliza acciones de cacheo nativas de GitHub para acelerar la instalación de dependencias de `pip`.

---

## 2. Entrenamiento y Validación (CT) - `retrain.yml`

**Propósito:** Automatizar el entrenamiento del modelo de Machine Learning, validar sus métricas de rendimiento y gestionar su versionado mediante tags de Git.

- **Activación (Triggers):**
  - Cambios en los archivos de entrenamiento (`model/train.py`, `model/requirements.txt`) en la rama `master`.
  - Programación cron: Todos los lunes a las 02:00 AM UTC.
  - Ejecución manual (`workflow_dispatch`) con parámetros opcionales para umbrales de métricas.
- **Entorno:** - `MLFLOW_TRACKING_URI`: Se conecta al servidor de MLflow (vía secretos) o utiliza almacenamiento local como respaldo.
- **Etapas clave:**
  1. **Entrenamiento:** Ejecuta el script de entrenamiento del modelo.
  2. **Validación (Quality Gate):** Comprueba que el `accuracy` y `f1-score` sean mayores a 0.80 (o los valores definidos). Si fallan, el pipeline se detiene.
  3. **Artefactos:** Sube los pesos del modelo (`model.pkl`) y los reportes de métricas como artefactos de la ejecución.
  4. **Tagging:** Si el entrenamiento es exitoso en `master`, genera un nuevo tag automático con formato `vYYYYMMDDHHMMSS`.
  5. **Release:** Crea una GitHub Release con el resumen de métricas del nuevo modelo.

---

## 3. Construcción y Despliegue (CD) - `deploy.yml`

**Propósito:** Empaquetar la aplicación en una imagen de contenedor Docker, publicarla en GitHub Container Registry (GHCR) y realizar pruebas de humo (smoke tests) para validar el despliegue.

- **Activación (Triggers):**
  - Creación de cualquier tag que comience por `v*` (disparado automáticamente por `retrain.yml`).
  - Ejecución manual para despliegues rápidos.
- **Trabajos (Jobs):**
  - **build-push:** - Extrae metadatos y genera etiquetas (SemVer y SHA).
    - Compila la imagen Docker de la API.
    - Publica la imagen en `ghcr.io`.
  - **smoke-test:**
    - Levanta temporalmente el stack completo (`mlflow`, `otel-collector` y la nueva imagen de la `api`) usando Docker Compose.
    - Espera a que el endpoint `/health` de la API responda exitosamente.
    - Realiza una petición de inferencia de prueba para confirmar que el modelo se carga y responde correctamente (HTTP 200).
    - Destruye el entorno temporal de prueba.

---

## Seguridad y Permisos

- **GITHUB_TOKEN:** Se utiliza para autenticarse contra GHCR y para crear releases y tags.
- **Secretos requeridos:** - `MLFLOW_TRACKING_URI`: URL del servidor MLflow remoto.
- **Paquetes:** Las imágenes se almacenan en GitHub Packages bajo el nombre del repositorio.

---

## Flujo de Trabajo Típico

1. Push a `develop` -> Activación de `ci.yml`.
2. Merge a `master` -> Activación de `retrain.yml`.
3. Éxito en entrenamiento -> Creación del tag `vYYYYMMDDHHMMSS`.
4. Creación del tag -> Activación de `deploy.yml`.
5. Éxito en tests de humo -> Imagen lista en registro OCI para entornos de producción.
