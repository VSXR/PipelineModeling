# PipelineModeling - Guía de Proyecto para IA

## Operaciones CLI
| Comando | Acción |
|---|---|
| `python manage.py setup` | Configuración inicial y creación del entorno virtual |
| `python manage.py start` | Arranque del stack completo |
| `python manage.py stop` | Parada de todos los servicios |
| `python manage.py status` | Verificación de estado de servicios |
| `python manage.py simulate --scenario all` | Ejecución de todos los escenarios de resiliencia |

## Testing
| Comando | Alcance |
|---|---|
| `python manage.py test` | Suite completa |
| `python manage.py test --unit` | Unitarios excluyendo infraestructura API |
| `python manage.py test --integration` | Integración de observabilidad y API |

## Arquitectura y Estándares
- **Separación de espacios:** Aislamiento absoluto entre el código fuente y los datos de ejecución.
- **Principios:** Aplicación estricta de SOLID y DRY.
- **Paradigma:** Enfoque funcional y declarativo preferente.
- **Gestión de modelos:** MLflow Model Registry opera como fuente de verdad exclusiva para los artefactos. El registro requiere superar umbrales de métricas predefinidos.
- **Flujos automatizados:** Workflows de GitHub Actions independientes para integración continua, reentrenamiento continuo y despliegue continuo.
- **Telemetría:** Emisión nativa vía OpenTelemetry hacia OTel Collector, exportación a Prometheus y visualización en Grafana.

## Reglas de Interacción
- Estructurar el texto exclusivamente mediante párrafos, listas y tablas.
- Eliminar preámbulos, transiciones y explicaciones elementales.
- Evitar el uso de comillas simples en el texto narrativo.
- Mantener los bloques de código limpios de comentarios, documentando únicamente las decisiones arquitectónicas no evidentes.
- Identificar casos borde y fallos potenciales antes de proponer implementaciones.
- Solicitar parámetros adicionales mediante una lista de variables necesarias si la información inicial resulta insuficiente.
