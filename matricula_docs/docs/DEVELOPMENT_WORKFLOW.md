# Flujo de desarrollo

Este documento describe cómo se construye el software de forma incremental: en iteraciones cortas, integrando cambios frecuentes al repositorio y priorizando lo que agrega valor antes que lo que suena impresionante.

## 1. Filosofía

No se construye el sistema de una sentada. Se construye en **iteraciones pequeñas** que cumplen tres condiciones:

1. **Cada iteración deja algo funcionando.** Nunca se termina un ciclo con el sistema roto o a medias.
2. **Cada iteración es desplegable.** El código merged a `main` puede subirse a producción en cualquier momento.
3. **Cada iteración se prueba antes de mergear.** Sin excepciones.

Este enfoque se llama **desarrollo incremental** y es lo contrario del "big bang" (construir todo aislado y unir al final, con desastre garantizado).

## 2. Fases del proyecto

El desarrollo se organiza en cinco fases secuenciales. Cada fase termina con un release funcional que se puede mostrar y probar.

### Fase 0 — Fundación (semana 1)

**Objetivo:** dejar la infraestructura de desarrollo lista para que las siguientes fases avancen sin fricción.

**Entregables:**
- Repositorio inicializado con la estructura de carpetas de `docs/ARCHITECTURE.md`.
- `docker-compose.yml` que levanta PostgreSQL + Redis + backend en desarrollo.
- `Dockerfile` del backend y del frontend.
- Pipeline de CI configurado (`ci.yml` corriendo en cada push).
- `pyproject.toml` con dependencias base fijadas.
- Migración inicial de Alembic vacía (para inicializar el sistema de migraciones).
- Un endpoint `/health` funcionando y probado.
- README con instrucciones para arrancar el proyecto localmente.

**Definición de terminado:** un compañero clona el repo, ejecuta `docker-compose up` y ve el `/health` respondiendo en dos minutos.

### Fase 1 — Autenticación (semana 2)

**Objetivo:** poder identificar usuarios y proteger endpoints.

**Entregables:**
- Modelos `User`, `Student`, `Administrator` con sus migraciones.
- Endpoint `POST /auth/login` que retorna JWT.
- Middleware de autenticación que valida el token en cada request.
- Endpoint `GET /students/me` protegido.
- Tests unitarios de casos de uso de autenticación.
- Tests de integración del flujo login → endpoint protegido.

**Definición de terminado:** un estudiante se autentica y consulta su perfil.

### Fase 2 — Catálogo académico (semana 3)

**Objetivo:** exponer la oferta de materias y grupos.

**Entregables:**
- Modelos `Program`, `Course`, `Prerequisite`, `Professor`, `EnrollmentPeriod`, `CourseOffering`, `ScheduleBlock` con migraciones.
- Endpoints `GET /courses`, `GET /courses/{id}`, `GET /courses/{id}/offerings`, `GET /offerings/{id}`.
- Seed script con datos de prueba (3 programas, 15 materias, 20 ofertas).
- Caché de Redis para las consultas de catálogo (TTL 30 segundos).
- Tests unitarios y de integración de las consultas.

**Definición de terminado:** un estudiante consulta el catálogo y ve los grupos disponibles con sus cupos actuales.

### Fase 3 — Inscripción (semanas 4-5)

**Objetivo:** el corazón del sistema. Un estudiante puede inscribir materias con todas las validaciones y sin sobrecupo.

**Entregables:**
- Modelo `Enrollment` con migración.
- Servicios de dominio: `PrerequisiteValidator`, `ScheduleConflictDetector`.
- Caso de uso `EnrollStudentUseCase` con transacción y bloqueo optimista.
- Caso de uso `CancelEnrollmentUseCase`.
- Endpoints `POST /enrollments`, `DELETE /enrollments/{id}`, `GET /students/me/schedule`.
- **Tests de concurrencia:** simulación de 100 solicitudes simultáneas al último cupo con verificación de que solo una tenga éxito.
- Manejo de excepciones específicas (`CapacityExceededError`, `PrerequisitesNotMetError`, etc.).

**Definición de terminado:** 100 estudiantes concurrentes intentando el mismo último cupo, exactamente uno lo obtiene, los otros 99 reciben `409 Conflict`. Prueba automatizada.

Esta fase es la más importante y la que más se debe probar. Merece dos semanas.

### Fase 4 — Administración y reportes (semana 6)

**Objetivo:** herramientas para el personal académico.

**Entregables:**
- Endpoints administrativos: crear períodos, crear ofertas, ajustar cupos.
- Endpoint `PUT /admin/enrollment-periods/{id}/activate`.
- Reportes: inscripciones por programa, ocupación por grupo.
- Autorización basada en rol (solo `ADMIN`).
- Tests de autorización (un estudiante intentando llamar endpoints de admin debe recibir 403).

**Definición de terminado:** un administrador puede abrir un período de matrícula, crear grupos y ver el reporte de inscripciones en tiempo real.

### Fase 5 — Frontend y comprobante (semana 7)

**Objetivo:** interfaz para el estudiante y generación de comprobantes.

**Entregables:**
- Frontend React con las vistas: login, catálogo, mis inscripciones, horario.
- Consumo de la API con TanStack Query.
- Manejo de errores de la API (mensajes claros al usuario).
- Endpoint `GET /students/me/receipt` que genera PDF.
- Tests del frontend con Vitest y Testing Library.

**Definición de terminado:** un estudiante realiza todo el proceso de matrícula desde la interfaz web y descarga su comprobante en PDF.

## 3. Ritmo de trabajo dentro de cada fase

### Iteraciones de 2 a 3 días

Cada fase se subdivide en **iteraciones cortas** de 2-3 días. El trabajo ocurre directamente sobre `develop` (ver `CI_CD.md` sección 3: cuatro ramas permanentes, sin ramas por funcionalidad). Cada iteración:

1. Se hacen commits pequeños y frecuentes con mensajes claros, sobre `develop`.
2. Se pushea al menos una vez al día, para que el CI corra y para no perder trabajo.
3. Se hace **auto-revisión** (o con `@code-reviewer` de Claude Code) antes de cerrar la iteración.
4. El CI tiene que estar verde antes de dar la iteración por terminada.
5. Cuando la fase completa está lista, se mergea `develop` → `qa` para validarla a mano.

### Regla de oro: nunca dejar `develop` roto

Sin ramas por funcionalidad, `develop` es a la vez donde se trabaja y de donde sale lo que llega a producción. Puede romperse un momento mientras se desarrolla, pero **nunca se deja rota al terminar la jornada**: si el CI se pone rojo, arreglarlo es la máxima prioridad y no empieza trabajo nuevo hasta que vuelva a verde.

La disciplina que antes garantizaba el Pull Request se traslada al commit: cada commit que se empuja debe dejar la suite en verde. Es más exigente, no menos.

### Un solo tema por commit

Un commit resuelve una cosa. No se mezclan cambios de interfaz con refactor de dominio en el mismo commit: eso hace imposible revisar la historia y revertir con precisión. Si aparece un bug mientras se implementa una funcionalidad, se arregla en su propio commit.

## 4. Cómo se decide qué hacer primero

Cada fase tiene entregables ordenados. Dentro de una fase, el orden se decide por **dependencia técnica**, no por gusto.

Ejemplo de Fase 3 (Inscripción):

1. Modelo `Enrollment` y migración (nada funciona sin la tabla).
2. `PrerequisiteValidator` (dominio puro, se prueba solo).
3. `ScheduleConflictDetector` (dominio puro, se prueba solo).
4. `EnrollStudentUseCase` (usa los validadores).
5. Endpoint `POST /enrollments` (usa el caso de uso).
6. Tests de concurrencia (necesitan el endpoint funcionando).

Ir en este orden significa que **cada paso deja algo probado antes de construir sobre él**. Al revés (empezar por el endpoint) se llega al final con un montón de código no probado y errores acumulados.

## 5. Definición de "terminado"

Un ítem no está terminado cuando "el código funciona en mi máquina". Está terminado cuando:

- [ ] Cumple los criterios de aceptación de la fase.
- [ ] Tiene tests unitarios de casos de uso y del dominio.
- [ ] Tiene test de integración si toca base de datos o red.
- [ ] Pasa `black`, `isort`, `mypy`.
- [ ] No introduce nuevas advertencias en el linter.
- [ ] Está documentado (docstring en funciones públicas).
- [ ] El endpoint aparece en la documentación OpenAPI si aplica.
- [ ] Se abre PR, CI verde, revisión aprobada, merge.

## 6. Manejo de deuda técnica

**Deuda técnica es normal y esperada.** Lo que no es aceptable es que sea invisible.

Cada vez que se toma un atajo consciente (ej. "por ahora no valido este caso raro porque no da tiempo"), se registra:

1. Comentario `TODO(sebas, fecha): descripción` en el código.
2. Issue en GitHub con etiqueta `technical-debt`.
3. Se atiende en el siguiente sprint o cuando bloquee algo.

La deuda invisible es la que mata proyectos. La visible se gestiona.

## 7. Cómo se maneja un cambio grande sin bloquear a nadie

Cuando una feature es grande y toma más de una iteración, se usa **feature flag** o **branch by abstraction**:

- El código nuevo se integra a `develop` desactivado por defecto.
- Solo se activa en el ambiente donde se está probando.
- Cuando está listo, se activa en producción cambiando la configuración, no el código.

Esto evita ramas gigantes que se desincronizan de `develop` durante semanas y luego son un dolor mergear.

## 8. Retrospectivas cortas al final de cada fase

Al cerrar una fase, media hora de retrospectiva:

- **¿Qué salió bien?** Para repetirlo.
- **¿Qué salió mal?** Para no repetirlo.
- **¿Qué aprendí?** Para documentarlo si aplica al equipo.

En un proyecto académico individual, esto puede ser una nota rápida en un archivo `docs/RETROSPECTIVES.md`. En un proyecto de equipo, una reunión de 30 minutos.

## 9. Anti-patrones a evitar

- **Rama gigante que vive semanas** sin mergear. Se desincroniza y el merge es un infierno.
- **Merge sin revisión propia** ("total es solo un cambio pequeño"). Los bugs entran por ahí.
- **Deshabilitar tests** para que el CI pase. Es tapar el problema, no resolverlo.
- **Commits vagos** como "fix", "cambios", "asdf". Nadie entiende la historia después.
- **Empezar por el frontend** antes de que el backend responda. El frontend queda mockeado con datos fake y luego no calza con el contrato real.
- **Refactorizar mientras se implementa una feature nueva.** Un cambio a la vez. Refactor va en su propia rama.
- **Deployar el viernes por la tarde.** Sin comentarios.

## 10. Alineación con CI/CD

El flujo de desarrollo y el pipeline de CI/CD son dos caras de la misma moneda:

| Acción del desarrollador | Reacción del pipeline |
|---|---|
| `git push feature/x` | Corre `ci.yml`: lint + tests + escaneos |
| PR aprobado, merge a `develop` | Corre `deploy-dev.yml`: sube a ambiente DEV |
| PR aprobado, merge a `main` | Corre `deploy-staging.yml`: sube a STAGING + E2E |
| Aprobación manual en GitHub | Corre `deploy-prod.yml`: rolling deploy a PROD |

Cada paso del desarrollo dispara automatización. El objetivo es que el desarrollador se concentre en el código, no en operar servidores.

## 11. Herramientas de apoyo

- **GitHub Issues** para tickets y bugs.
- **GitHub Projects** (Kanban) para visualizar el progreso de la fase.
- **Etiquetas de issue**: `feature`, `bug`, `technical-debt`, `docs`, `blocked`.
- **Milestones** para agrupar issues por fase (`Fase 3 — Inscripción`).

Nada de esto es obligatorio, pero para un proyecto académico que se sustenta, un tablero con las fases y su avance es un excelente material de apoyo visual.

## 12. Comandos que aceleran el flujo

Un `Makefile` en la raíz reduce fricción:

```makefile
.PHONY: dev test lint format migrate seed clean

dev:
	docker-compose up -d
	@echo "Backend en http://localhost:8000"

test:
	docker-compose exec backend pytest

test-unit:
	docker-compose exec backend pytest -m unit

test-int:
	docker-compose exec backend pytest -m integration

lint:
	docker-compose exec backend black --check app tests
	docker-compose exec backend isort --check-only app tests
	docker-compose exec backend mypy app

format:
	docker-compose exec backend black app tests
	docker-compose exec backend isort app tests

migrate:
	docker-compose exec backend alembic upgrade head

migrate-create:
	docker-compose exec backend alembic revision --autogenerate -m "$(msg)"

seed:
	docker-compose exec backend python -m app.infrastructure.seed

clean:
	docker-compose down -v
```

`make dev`, `make test`, `make lint` son comandos que se aprenden en un minuto y se usan cien veces al día.

---

## Referencias entre documentos

- Las convenciones de commits, ramas y PRs están en `docs/BEST_PRACTICES.md`.
- El pipeline técnico completo está en `docs/CI_CD.md`.
- La arquitectura que sostiene esta división de trabajo está en `docs/ARCHITECTURE.md`.
- Los subagentes que aceleran cada fase están en `docs/CLAUDE_CODE_AGENTS.md`.
