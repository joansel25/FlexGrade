---
name: estado-del-software
description: Memoria viva del Sistema de Matrícula. Consúltala ANTES de escribir código, proponer un diseño o retomar el trabajo tras un corte, y ACTUALÍZALA al cerrar cada iteración. Contiene dónde vive cada pieza (backend, PostgreSQL, Redis), qué está construido y qué no, las decisiones ya tomadas que no se vuelven a discutir, y el protocolo de actualización. Úsala también cuando la pregunta sea "¿por qué está hecho así?" o "¿en qué punto vamos?".
---

# Estado del software — Sistema de Matrícula

> **Actualizada al cerrar la iteración 4.4 (Fase 4 completa).** Última verificación real:
> `pytest` completo en verde con 439 tests y `mypy --strict` sin incidencias sobre 137 archivos.

Este archivo es la memoria del proyecto entre sesiones. `CLAUDE.md` dice cómo se trabaja; esto
dice **en qué punto está el software y por qué está hecho así**. Si los dos se contradicen,
manda `CLAUDE.md` y hay que corregir este archivo.

## 1. Dónde vive cada cosa

Todo el desarrollo local corre en Docker Compose, proyecto `matricula` (`docker-compose.yml` en
la raíz). Nada se ejecuta en el host: los comandos van por `docker-compose exec backend ...`.

| Pieza | Dónde | Detalle que hay que recordar |
|---|---|---|
| Backend | contenedor `matricula-backend-1`, `http://localhost:8000` | FastAPI + uvicorn, código montado en `/app` con recarga en caliente. Etapa `dev` del Dockerfile (trae pytest, black, isort, mypy) |
| PostgreSQL | contenedor `matricula-postgres-1`, `localhost:5432` | Imagen `postgres:16`, base `matricula`, usuario `matricula`. Volumen `pgdata`. **Los tests usan otra base: `matricula_test`**, que crea y migra `tests/integration/conftest.py` |
| Redis | contenedor `matricula-redis-1`, `localhost:6379` | Imagen `redis:7`, base lógica **0** en desarrollo y **1** en los tests (`tests/conftest.py` reescribe la URL) |
| Migraciones | Alembic, dentro del backend | Los tests corren `alembic upgrade head`, nunca `create_all`: así prueban el esquema real, con triggers, índices parciales y `CHECK` |
| Configuración | `app/infrastructure/config/settings.py` (Pydantic Settings) | `DATABASE_URL`, `REDIS_URL` y `JWT_SECRET` son obligatorios; sin ellos la app no arranca. En AWS los inyecta Elastic Beanstalk desde Secrets Manager |

Comandos que se usan de verdad (equivalentes en el `Makefile`):

```bash
docker-compose up -d                                   # make dev
docker-compose exec backend pytest -q                  # make test
docker-compose exec backend pytest -m unit -q          # sin base de datos
docker-compose exec backend alembic upgrade head       # make migrate
docker-compose exec backend python -m app.infrastructure.seed   # make seed (idempotente)
docker-compose exec backend black app tests && docker-compose exec backend isort app tests
docker-compose exec backend mypy app                   # make lint
```

**Nunca corras dos suites a la vez.** Los tests de integración vacían tablas enteras de
`matricula_test` y comparten la base lógica 1 de Redis: dos `pytest` simultáneos se borran los
datos entre sí y fallan en sitios que no tienen nada que ver con el cambio que estés probando.

## 2. Arquitectura, en una pantalla

Hexagonal. Las dependencias apuntan siempre al centro.

```
interfaces/api/routers  →  application/use_cases  →  domain/
        ↓ (DI)                     ↑ (puertos)
interfaces/api/dependencies/di.py ─┴─→ infrastructure/ (SQLAlchemy, Redis, JWT)
```

- `di.py` es el **único** sitio donde un puerto se resuelve a un adaptador concreto.
- Los routers son delgados: traducen schema ↔ entidad/DTO y no deciden nada.
- Las excepciones de dominio se traducen a HTTP en **un solo mapa**, `_MAPEO_ERRORES` de
  `main.py`. Una excepción sin entrada ahí cae en `400 DOMAIN_ERROR`, así que al añadir una hay
  que registrarla.
- Formato de error universal: `{"error": {"code", "message", "details"}}`. Los `401` llevan
  además `WWW-Authenticate: Bearer`.

## 3. Las decisiones que ya están tomadas

No se vuelven a discutir sin una razón nueva. Cada una está explicada en el código, en el sitio
donde importa.

1. **El sobrecupo es imposible por dos defensas, no por una.** `try_reserve_slot` es un único
   `UPDATE ... WHERE enrolled_count < total_capacity` (sin lectura previa), y por debajo está el
   `CHECK (enrolled_count <= total_capacity)` de PostgreSQL.
2. **El descuento de cupo NO usa bloqueo optimista por `version`.** Se probó y no escala: con N
   transacciones sobre la misma fila solo gana una por ronda, y se rechazaban cupos que existían.
   `version` sigue existiendo y se usa donde la contención sí es rara: `update_capacity`.
3. **La disponibilidad de cupos nunca se cachea.** El catálogo sí (Redis, TTL 30 s, claves
   `catalog:v1:...`). El detalle de un grupo se sirve de caché salvo `enrolled_count`, que se
   relee siempre de PostgreSQL.
4. **La caché se invalida FUERA de la transacción y solo tras confirmarla.** Invalidar dentro y
   revertir después dejaría la caché repoblada con el valor viejo.
5. **La caché nunca hace fallar una petición.** Entrada ilegible o Redis caído ⇒ se va a
   PostgreSQL. El adaptador lleva cortacircuitos y por eso su instancia es única por proceso.
6. **Rol ADMIN declarado una vez, en el router**, no endpoint por endpoint.
7. **Los reportes se calculan en vivo**, agregando en SQL con `GROUP BY`. Nunca se cachean.
8. **Un grupo se abre siempre en el período activo**, que no viaja en la petición.
9. **Los códigos de materia se normalizan** en el value object `CourseCode` antes de comprobar
   duplicados; si no, `mat101` y `MAT101` convivirían.

## 4. Qué está construido

| Fase | Estado | Endpoints |
|---|---|---|
| 0 — Fundación | ✅ | `/health` |
| 1 — Autenticación | ✅ | `POST /auth/login`, `/auth/refresh`, `/auth/logout`, `GET /students/me` |
| 2 — Catálogo | ✅ | `GET /courses`, `/courses/{id}`, `/courses/{id}/offerings`, `/offerings/{id}`, `/enrollment-periods/current` |
| 3 — Inscripción | ✅ | `POST /enrollments`, `DELETE /enrollments/{id}`, `GET /students/me/schedule` |
| 4 — Admin y reportes | ✅ | ver desglose abajo |
| 5 — Frontend y comprobante | ⬜ pendiente | SPA React + `GET /students/me/receipt` (PDF) |

Desglose de la Fase 4 por iteraciones (la numeración es nuestra; los documentos solo describen
la fase completa):

| Iteración | Entregable | Commit |
|---|---|---|
| 4.1 | Autorización por rol y formato de error unificado | `07b3215` |
| 4.2 | Ventanas de matrícula: crear, activar, listar | `346915d` |
| 4.3 | Catálogo y cupos: `POST /admin/courses`, `POST /admin/offerings`, `PUT /admin/offerings/{id}/capacity` | `34005b8` |
| 4.4 | Reportes: `GET /admin/reports/enrollments`, `GET /admin/reports/occupancy` | esta iteración |

Ausencias **intencionales** (no son deuda, no las implementes por iniciativa propia): la lista
de espera automática — `WAITLISTED` existe en el enum pero ninguna operación lo produce.

Ausencias que sí son deuda, pendientes de decidir cuándo se pagan:

- **Rate limiting.** `API.md` fija límites por endpoint (login 5/min por IP, inscripción 30/min,
  catálogo 120/min, admin 60/min) y no hay nada implementado.
- **`GET /enrollment-periods` público.** `API.md` sección 5 lo documenta como listado paginado
  de períodos; el único listado que existe es `GET /admin/enrollment-periods`, que exige rol
  ADMIN.

## 5. Mapa rápido del código

```
backend/app/
├── domain/            entidades, value objects, servicios y excepciones. Sin dependencias
├── application/
│   ├── ports/         interfaces (repositorios, caché, auth, unit of work)
│   ├── dtos/          solo cuando el resultado compone varios agregados
│   └── use_cases/     auth · catalog · enrollment · admin
├── infrastructure/    SQLAlchemy (models + repositories), Redis, JWT, settings, seed
└── interfaces/api/    routers · schemas · dependencies (auth + di)

backend/tests/
├── unit/          sin base de datos. `doubles.py` (dobles de los puertos) y `factories.py`
├── integration/   contra PostgreSQL y Redis reales. `conftest.py` trae la fixture `catalogo`
└── e2e/
```

Al añadir un puerto hay que tocar cuatro sitios: el puerto, el adaptador SQL, `di.py` y el
doble en `tests/unit/doubles.py`. Olvidar el último rompe todos los tests que instancian ese
doble, porque la clase abstracta deja de poder construirse.

## 6. Protocolo de actualización

**Al cerrar cada iteración, antes del commit**, revisa este archivo y actualiza:

1. La línea de "Actualizada al cerrar…" del encabezado, con las cifras reales de `pytest` y
   `mypy` que acabas de ver (no de memoria).
2. La tabla de fases y el desglose de iteraciones, con el hash del commit.
3. La sección 3 **solo si se tomó una decisión nueva** que cambie cómo se construye algo. Una
   decisión que ya está ahí no se reescribe.
4. La sección 1 si cambió dónde vive algo: puerto, servicio, base de datos, variable obligatoria.

Reglas para que este archivo siga sirviendo:

- **Nada que el repositorio ya diga mejor.** Aquí no se copian firmas de funciones, esquemas de
  tablas ni contratos de endpoints: para eso están `API.md`, `DATA_MODEL.md` y el código.
- **Cada afirmación, verificada.** Si dices que algo está hecho, es porque lo viste pasar, no
  porque el plan lo prometía.
- **Corrige lo que se quedó viejo.** Una línea desactualizada aquí es peor que no tenerla:
  se lee como si fuera cierta.
