# Sistema de Matrícula y Gestión Académica

Aplicación web escalable para la inscripción de materias en instituciones de educación superior, diseñada para soportar picos de hasta 5.000 estudiantes concurrentes durante las ventanas de matrícula y operar con costos alineados al uso real durante el resto del semestre.

## Contexto del proyecto

Este es el desarrollo del software para el proyecto de la asignatura de **Computación en la Nube**. La arquitectura de despliegue en la nube (AWS, modelo PaaS, VPC Multi-AZ) ya está definida en los documentos de la Fase I. Este repositorio contiene la aplicación que se ejecutará sobre esa infraestructura.

## Problema que resuelve

Durante las ventanas de matrícula académica, miles de estudiantes intentan inscribirse simultáneamente en un lapso de pocas horas. Los sistemas tradicionales colapsan bajo esa carga, lo que genera caídas del servicio, inscripciones duplicadas, sobrecupo en grupos y estudiantes que pierden cupos por fallas técnicas.

Este software aborda tres puntos críticos:

1. **Concurrencia extrema controlada.** Miles de solicitudes simultáneas sin sobrecupo ni inscripciones duplicadas, garantizando consistencia transaccional en el descuento de cupos.
2. **Integración centralizada.** Toda la información académica (materias, grupos, horarios, cupos, prerrequisitos) en un único punto de verdad.
3. **Escalabilidad económica.** La infraestructura crece durante los picos y se reduce el resto del semestre, sin sobredimensionar recursos.

## Stack tecnológico

**Backend**
- Python 3.12 con FastAPI (API REST)
- SQLAlchemy 2.x (ORM)
- Alembic (migraciones de base de datos)
- Pydantic v2 (validación de esquemas)
- pytest (pruebas)

**Persistencia**
- PostgreSQL 16 (base de datos principal)
- Redis 7 (caché de consultas frecuentes y control de sesiones)

**Frontend**
- React 18 con TypeScript
- Vite (build)
- TanStack Query (manejo de estado del servidor)

**Infraestructura (para despliegue)**
- Docker y Docker Compose (desarrollo local)
- AWS Elastic Beanstalk (backend), S3 + CloudFront (frontend), RDS PostgreSQL Multi-AZ, ElastiCache Redis, Cognito (autenticación)

## Estructura del repositorio

```
matricula-academica/
├── backend/                    # API en Python + FastAPI
│   ├── app/
│   │   ├── domain/             # Núcleo del negocio (entidades, reglas)
│   │   ├── application/        # Casos de uso y puertos
│   │   ├── infrastructure/     # Adaptadores concretos (DB, cache, auth)
│   │   └── interfaces/         # API REST (routers, schemas)
│   ├── tests/
│   ├── alembic/                # Migraciones de base de datos
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── README.md               # Guía específica del backend
│
├── frontend/                   # SPA en React + TypeScript
│   ├── src/
│   │   ├── features/           # Módulos por dominio (auth, courses, enrollment)
│   │   ├── shared/             # Componentes y utilidades compartidos
│   │   └── app/                # Configuración de rutas y providers
│   ├── Dockerfile
│   ├── package.json
│   └── README.md               # Guía específica del frontend
│
├── docs/                       # Documentación técnica del proyecto
│   ├── DATA_MODEL.md           # Modelo de datos y esquema SQL
│   ├── API.md                  # Especificación de endpoints
│   ├── ARCHITECTURE.md         # Arquitectura hexagonal y principios SOLID
│   ├── BEST_PRACTICES.md       # Convenciones y buenas prácticas
│   ├── CI_CD.md                # Pipeline de integración y despliegue continuos
│   ├── DEVELOPMENT_WORKFLOW.md # Fases del proyecto y desarrollo incremental
│   └── CLAUDE_CODE_AGENTS.md   # Prompt para subagentes de Claude Code
│
├── .github/
│   └── workflows/              # Workflows de GitHub Actions (CI/CD)
│       ├── ci.yml              # Lint + tests + escaneos (todas las ramas)
│       ├── deploy-dev.yml      # Despliegue automático a DEV (rama develop)
│       ├── deploy-staging.yml  # Despliegue automático a STAGING (rama main)
│       ├── deploy-prod.yml     # Despliegue manual a PROD con aprobación
│       └── rollback-prod.yml   # Rollback de emergencia
│
├── Makefile                    # Comandos frecuentes (make dev, test, lint)
├── docker-compose.yml          # Entorno local (backend + Postgres + Redis)
├── CLAUDE.md                   # Contexto persistente para Claude Code
└── README.md                   # Este archivo
```

## Módulos funcionales

El sistema se organiza alrededor de cinco módulos que reflejan el dominio del negocio, no las capas técnicas:

| Módulo | Responsabilidad | Casos de uso principales |
|---|---|---|
| **Autenticación** | Identificar usuarios y controlar acceso por rol | Login, logout, refresh token |
| **Catálogo académico** | Exponer la oferta de materias y grupos | Listar materias, ver grupos, consultar cupos |
| **Inscripciones** | Registrar, validar y cancelar matrículas | Inscribir, cancelar, ver horario propio |
| **Administración académica** | Gestionar la configuración del período | Abrir período, crear grupos, ajustar cupos |
| **Reportes** | Consultar métricas del proceso | Ocupación por materia, inscripciones por programa |

## Documentación técnica

Toda la documentación de diseño e implementación está en la carpeta `docs/`:

- **[Modelo de datos](docs/DATA_MODEL.md)** — entidades, relaciones y esquema SQL completo.
- **[API REST](docs/API.md)** — endpoints, ejemplos de request/response, códigos de error.
- **[Arquitectura](docs/ARCHITECTURE.md)** — arquitectura hexagonal, aplicación de SOLID, diagramas de paquetes y clases.
- **[Buenas prácticas](docs/BEST_PRACTICES.md)** — convenciones de código, testing, git, seguridad.
- **[Flujo de desarrollo](docs/DEVELOPMENT_WORKFLOW.md)** — fases del proyecto, iteraciones, orden de trabajo.
- **[CI/CD](docs/CI_CD.md)** — pipeline de integración y despliegue continuos con GitHub Actions.
- **[Claude Code Agents](docs/CLAUDE_CODE_AGENTS.md)** — configuración de subagentes para acelerar el desarrollo.

## Ejecución local

```bash
# Levantar el entorno completo (Postgres + Redis + backend)
docker-compose up -d

# Aplicar migraciones
docker-compose exec backend alembic upgrade head

# Cargar datos de ejemplo
docker-compose exec backend python -m app.infrastructure.seed

# La API queda disponible en http://localhost:8000
# La documentación interactiva en http://localhost:8000/docs
```

## Estado del proyecto

Este README y los documentos en `docs/` constituyen el diseño detallado del sistema, listo para iniciar la implementación. El desarrollo se realizará de manera incremental respetando la arquitectura y las convenciones documentadas.

## Autor

Joan Sebastián Cárdenas Gutiérrez
Tecnología en Análisis y Desarrollo de Software — Institución Universitaria Tecnológico de Antioquia
