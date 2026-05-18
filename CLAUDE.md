# PipelineModeling: Contexto Operativo y Arquitectura

Sistema de aprendizaje continuo para clasificación binaria basado en el dataset Breast Cancer Wisconsin. Implementa el ciclo CRISP-DM con inferencia en tiempo real, reentrenamiento incremental y observabilidad completa.

## Stack Tecnológico y Servicios

* **api** (FastAPI, :8000): Inferencia, entrenamiento (SGDClassifier) y gestión de versiones.
* **frontend** (Streamlit, :8501): Panel de control MLOps.
* **seeder** (Python Async): Inyección de tráfico sintético y simulación de deriva de datos (drift).
* **mlflow** (MLflow, :5000): Registro de modelos y tracking de experimentos.
* **otel-collector** (OpenTelemetry, :4317): Recolección de telemetría gRPC.
* **prometheus** (Prometheus, :9090): Almacenamiento de series temporales.
* **grafana** (Grafana, :3000): Dashboards de observabilidad.

## Operaciones de Ciclo de Vida (manage.py)

* `setup`: Configuración inicial, dependencias y entrenamiento base.
* `start` / `stop`: Control del stack Docker Compose.
* `status`: Verificación de salud de los contenedores.
* `test`: Ejecución de pruebas (unitarias, integración, observabilidad).
* `simulate --scenario [drift|version-fail|training-errors|chaos|all]`: Pruebas de resiliencia y simulaciones.

## Estándares del Proyecto y Protocolo de Asistencia

* **Paradigmas**: Priorizar SOLID, DRY y diseño funcional/declarativo.
* **Estilo de Código**: Bloques limpios. Cero comentarios a menos que justifiquen decisiones arquitectónicas complejas.
* **Restricciones de Formato**: Prohibido el uso de comillas simples en texto narrativo. Prohibido el uso de blockquotes.
* **Evaluación Técnica**: Toda solución propuesta debe incluir una identificación explícita de casos borde, condiciones de carrera y fallos potenciales.
