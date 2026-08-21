# CLAUDE.md

Este archivo es la memoria persistente del proyecto para Claude Code. Lee esto siempre antes de proponer código o cambios.

## El proyecto

**Sistema de Matrícula y Gestión Académica**: aplicación web escalable para la inscripción de materias en instituciones de educación superior, diseñada para soportar picos de hasta 5.000 estudiantes concurrentes durante las ventanas de matrícula.

Es el desarrollo de software para el proyecto de la asignatura de **Computación en la Nube**. La arquitectura de despliegue en la nube (AWS, modelo PaaS, VPC Multi-AZ) ya está definida en los documentos de la Fase I.

## Stack tecnológico

**Backend**
- Python 3.12 + FastAPI (API REST)
- SQLAlchemy 2.x + Alembic (persistencia y migraciones)
- Pydantic v2 (validación)
- pytest, pytest-mock, Testcontainers (testing)

**Frontend**
- React 18 + TypeScript + Vite
- TanStack Query (state del servidor)

**Persistencia**
- PostgreSQL 16
- Redis 7 (caché)

**Infraestructura**
- Docker + Docker Compose (dev local)
- AWS Elastic Beanstalk + RDS PostgreSQL Multi-AZ + ElastiCache Redis + S3/CloudFront + Cognito (producción)

## Arquitectura

**Patrón:** Arquitectura Hexagonal (Ports & Adapters).

**Capas:**
- `domain/` — entidades, value objects, reglas de negocio. Sin dependencias externas.
- `application/` — casos de uso y puertos (interfaces).
- `infrastructure/` — adaptadores concretos (SQLAlchemy, Redis, etc).
- `interfaces/` — API REST con FastAPI.

**Regla de dependencias:** las dependencias siempre apuntan al centro. El dominio no conoce a nadie.

Detalles completos en `docs/ARCHITECTURE.md`.

## Convenciones críticas (aplicar siempre)

- **Type hints obligatorios** en Python. `mypy` en modo estricto.
- **Formato:** `black` + `isort`. Line length 100.
- **Sin `any` en TypeScript.** Modo estricto.
- **Nunca lógica de negocio en routers ni en modelos ORM.** Los routers son delgados; el ORM es solo persistencia.
- **Nunca imports de `infrastructure` en `domain` o `application`.** Si tienes que hacerlo, es un error de diseño.
- **Excepciones específicas del dominio.** Nunca `raise Exception`.
- **Tests para todo caso crítico:** inscripción (concurrencia), validación de prerrequisitos, autenticación.
- **Secretos en variables de entorno**, jamás en el código.
- **Commits siguen Conventional Commits:** `feat(scope): mensaje`.

Convenciones completas en `docs/BEST_PRACTICES.md`.

## Documentación de referencia

Lee estos archivos según la tarea:

| Archivo | Cuándo consultarlo |
|---|---|
| `docs/ARCHITECTURE.md` | Antes de crear módulos, puertos o servicios |
| `docs/DATA_MODEL.md` | Antes de modificar esquema o modelos ORM |
| `docs/API.md` | Antes de crear o modificar endpoints |
| `docs/BEST_PRACTICES.md` | Antes de cualquier commit |
| `docs/DEVELOPMENT_WORKFLOW.md` | Al planificar qué implementar y en qué orden |
| `docs/CI_CD.md` | Al modificar workflows, Dockerfile o deploy |
| `docs/CLAUDE_CODE_AGENTS.md` | Para entender los subagentes disponibles |

## Subagentes disponibles

Usa `@nombre-agente` para invocarlos:

- `@architect` — decisiones arquitectónicas, estructura, puertos.
- `@domain-expert` — entidades, value objects, reglas de negocio.
- `@api-developer` — routers FastAPI, schemas, dependencias.
- `@database-engineer` — modelos SQLAlchemy, migraciones, queries.
- `@testing-engineer` — tests unit, integration, e2e.
- `@devops-engineer` — Docker, CI/CD, AWS.
- `@frontend-developer` — componentes React, hooks, estado.
- `@code-reviewer` — revisión antes de commit.

## Comandos frecuentes

```bash
# Desarrollo local (levanta postgres + redis + backend)
docker-compose up -d

# Aplicar migraciones
docker-compose exec backend alembic upgrade head

# Crear una nueva migración
docker-compose exec backend alembic revision --autogenerate -m "descripción"

# Cargar datos de ejemplo (idempotente)
docker-compose exec backend python -m app.infrastructure.seed

# Correr tests
docker-compose exec backend pytest
docker-compose exec backend pytest -m unit          # solo unitarios (rápidos)
docker-compose exec backend pytest -m integration   # con DB
docker-compose exec backend pytest --cov=app        # con cobertura

# Linting y formato
docker-compose exec backend black app tests
docker-compose exec backend isort app tests
docker-compose exec backend mypy app

# Frontend
cd frontend && npm run dev
cd frontend && npm test
cd frontend && npm run build
```

## Reglas de oro

1. **No agregues carpetas ni archivos vacíos.** Cada archivo tiene un propósito.
2. **YAGNI:** no implementes lo que no está en los requisitos actuales.
3. **KISS:** la solución más simple que funciona es la correcta.
4. **Si dudas, pregunta.** Es preferible una pregunta a una decisión de diseño errada.
5. **Antes de mergear, corre los tests.** Sin excepciones.
