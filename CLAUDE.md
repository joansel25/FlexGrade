# CLAUDE.md

Memoria persistente del proyecto para Claude Code. Lee esto siempre antes de proponer código o
cambios.

> **Nota de estructura (pendiente de resolver):** la documentación técnica vive hoy en
> `matricula_docs/`, no en la raíz. Este archivo usa las rutas reales actuales. Existe además un
> `matricula_docs/CLAUDE.md` con el mismo contenido que Claude Code **no** carga automáticamente
> por estar fuera de la raíz. Cuando se decida la estructura definitiva del repositorio, hay que
> consolidar ambos en uno solo y actualizar las rutas de `.claude/agents/*.md`.

## El proyecto

**Sistema de Matrícula y Gestión Académica**: aplicación web escalable para la inscripción de
materias en instituciones de educación superior, diseñada para soportar picos de hasta **5.000
estudiantes concurrentes** durante las ventanas de matrícula, sin sobrecupo ni inscripciones
duplicadas.

Es el desarrollo de software para el proyecto de la asignatura de **Computación en la Nube**. La
arquitectura de despliegue (Azure, modelo PaaS, VNet con alta disponibilidad zonal) ya está definida en los documentos
de la Fase I.

## Stack tecnológico

**Backend**
- Python 3.12 + FastAPI (API REST)
- SQLAlchemy 2.x + Alembic (persistencia y migraciones)
- Pydantic v2 (validación)
- pytest, pytest-mock, Testcontainers (testing)

**Frontend**
- React 18 + TypeScript + Vite
- TanStack Query (estado del servidor)

**Persistencia**
- PostgreSQL 16
- Redis 7 (caché)

**Infraestructura**
- Docker + Docker Compose (dev local)
- Azure App Service + Azure Database for PostgreSQL Flexible Server + Azure Cache for Redis + Azure Storage + Front Door + Microsoft Entra External ID

## Arquitectura

**Patrón:** Arquitectura Hexagonal (Ports & Adapters).

- `domain/` — entidades, value objects, reglas de negocio. Sin dependencias externas.
- `application/` — casos de uso y puertos (interfaces).
- `infrastructure/` — adaptadores concretos (SQLAlchemy, Redis, JWT, SMTP).
- `interfaces/` — API REST con FastAPI.

**Regla de dependencias:** las dependencias siempre apuntan al centro. El dominio no conoce a
nadie.

Detalles completos en `matricula_docs/docs/ARCHITECTURE.md`.

## Convenciones críticas (aplicar siempre)

- **Type hints obligatorios** en Python. `mypy` en modo estricto.
- **Formato:** `black` + `isort`. Line length 100.
- **Sin `any` en TypeScript.** Modo estricto.
- **Nunca lógica de negocio en routers ni en modelos ORM.** Los routers son delgados; el ORM es
  solo persistencia.
- **Nunca imports de `infrastructure` en `domain` o `application`.** Si tienes que hacerlo, es
  un error de diseño.
- **Excepciones específicas del dominio.** Nunca `raise Exception`.
- **Tests para todo caso crítico:** inscripción (concurrencia), validación de prerrequisitos,
  detección de choque de horario, autenticación y autorización.
- **Secretos en variables de entorno**, jamás en el código.
- **Commits siguen Conventional Commits:** `feat(scope): mensaje`.

Convenciones completas en `matricula_docs/docs/BEST_PRACTICES.md`.

## El mecanismo que sostiene el requisito no funcional central

El descuento de cupo combina dos defensas complementarias; ninguna sustituye a la otra:

1. **Bloqueo optimista** con la columna `course_offerings.version` — el `UPDATE` usa
   `WHERE version = :expected` y reintenta un número limitado de veces si pierde la carrera.
2. **`CHECK (enrolled_count <= total_capacity)`** en PostgreSQL como red de seguridad final.

La disponibilidad de cupos **nunca se cachea**. El catálogo sí (Redis, TTL 30-60 s).

## Documentación de referencia

| Archivo | Cuándo consultarlo |
|---|---|
| `matricula_docs/docs/ARCHITECTURE.md` | Antes de crear módulos, puertos o servicios |
| `matricula_docs/docs/DATA_MODEL.md` | Antes de modificar esquema o modelos ORM |
| `matricula_docs/docs/API.md` | Antes de crear o modificar endpoints |
| `matricula_docs/docs/BEST_PRACTICES.md` | Antes de cualquier commit |
| `matricula_docs/docs/DEVELOPMENT_WORKFLOW.md` | Al planificar qué implementar y en qué orden |
| `matricula_docs/docs/CI_CD.md` | Al modificar workflows, Dockerfile o deploy |
| `matricula_docs/docs/CLAUDE_CODE_AGENTS.md` | Para entender los subagentes disponibles |

## Subagentes disponibles

Definidos en `.claude/agents/`. Invócalos por su nombre:

| Subagente | Cuándo usarlo |
|---|---|
| `architect` | Módulo nuevo, puerto nuevo, o dudar de en qué capa vive algo |
| `domain-expert` | Entidades, value objects, servicios de dominio, reglas académicas |
| `api-developer` | Routers FastAPI, schemas Pydantic, dependencias de inyección |
| `database-engineer` | Modelos SQLAlchemy, migraciones Alembic, repositorios, queries lentas |
| `testing-engineer` | Tests unit / integration / e2e, y reproducir bugs antes de arreglarlos |
| `devops-engineer` | Docker, docker-compose, GitHub Actions, Azure App Service, secretos |
| `frontend-developer` | Componentes React, hooks, TanStack Query, accesibilidad |
| `code-reviewer` | Revisión antes de commit o PR (solo lectura) |

Secuencias típicas: `architect` → `domain-expert` para un módulo nuevo; `database-engineer` →
`api-developer` para una feature con esquema nuevo; `testing-engineer` → `code-reviewer` antes de
cada commit.

## Fases del desarrollo

| Fase | Qué entrega |
|---|---|
| 0 — Fundación | Estructura, docker-compose, Dockerfile, CI, `/health` |
| 1 — Autenticación | User/Student/Admin, login JWT, endpoint protegido |
| 2 — Catálogo | Materias, grupos, caché Redis |
| 3 — Inscripción | Caso de uso crítico + test de concurrencia (dos semanas) |
| 4 — Admin y reportes | Endpoints admin, autorización por rol |
| 5 — Frontend | SPA React, comprobante PDF |

Detalle en `matricula_docs/docs/DEVELOPMENT_WORKFLOW.md`.

## Comandos frecuentes

```bash
# Desarrollo local (levanta postgres + redis + backend)
docker-compose up -d          # o: make dev

# Migraciones
docker-compose exec backend alembic upgrade head                          # make migrate
docker-compose exec backend alembic revision --autogenerate -m "mensaje"  # make migrate-create

# Datos de ejemplo (idempotente)
docker-compose exec backend python -m app.infrastructure.seed             # make seed

# Tests
docker-compose exec backend pytest                    # make test
docker-compose exec backend pytest -m unit            # make test-unit
docker-compose exec backend pytest -m integration     # make test-int
docker-compose exec backend pytest -m e2e             # make test-e2e
docker-compose exec backend pytest --cov=app

# Linting y formato
docker-compose exec backend black app tests           # make format
docker-compose exec backend isort app tests
docker-compose exec backend mypy app                  # make lint

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
