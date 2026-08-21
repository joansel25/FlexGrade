# Arquitectura del software

Este documento describe la arquitectura del backend del Sistema de Matrícula Académica: el patrón elegido, cómo se aplica en la estructura de carpetas, la aplicación concreta de los principios SOLID y los diagramas de paquetes y clases.

## 1. Patrón arquitectónico: Hexagonal (Ports & Adapters)

Se adopta **Arquitectura Hexagonal** (también conocida como Ports & Adapters o Clean Architecture) porque es la que mejor se ajusta a los objetivos del proyecto:

- **Separar el núcleo del negocio de la infraestructura.** La lógica de matrícula (validar prerrequisitos, descontar cupos, verificar horarios) no debe depender de PostgreSQL, Redis ni FastAPI. Debe poder ejecutarse y probarse sin ellos.
- **Facilitar cambios de infraestructura sin tocar el dominio.** Si mañana se cambia PostgreSQL por otra base de datos, o Cognito por otro proveedor de auth, el núcleo del software no cambia.
- **Habilitar testing rápido y confiable.** Los tests del dominio corren en milisegundos sin base de datos ni red.
- **Reflejar SOLID de forma natural.** El patrón obliga a usar inversión de dependencias y separación de responsabilidades.

### Las cuatro capas

```
┌─────────────────────────────────────────────────────────────┐
│                      INTERFACES                              │
│   (Adaptadores de entrada: FastAPI, CLI, workers)           │
│                                                              │
│   ┌──────────────────────────────────────────────────────┐  │
│   │                  APPLICATION                          │  │
│   │       (Casos de uso, orquestación, puertos)          │  │
│   │                                                       │  │
│   │   ┌─────────────────────────────────────────────┐    │  │
│   │   │              DOMAIN                          │    │  │
│   │   │  (Entidades, reglas de negocio puras)       │    │  │
│   │   └─────────────────────────────────────────────┘    │  │
│   │                                                       │  │
│   └──────────────────────────────────────────────────────┘  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ implementan puertos
                              │
┌─────────────────────────────────────────────────────────────┐
│                    INFRASTRUCTURE                            │
│  (Adaptadores de salida: SQLAlchemy, Redis, Cognito, SMTP)  │
└─────────────────────────────────────────────────────────────┘
```

**Regla de dependencias:** las flechas apuntan siempre hacia el centro. El dominio no conoce a nadie. La aplicación conoce al dominio. Infraestructura e interfaces conocen a la aplicación y al dominio.

### Responsabilidad de cada capa

| Capa | Contiene | No contiene |
|---|---|---|
| **Domain** | Entidades, value objects, reglas de negocio, excepciones de dominio | ORMs, HTTP, DBs, frameworks |
| **Application** | Casos de uso, puertos (interfaces), DTOs | Implementaciones concretas de infraestructura |
| **Infrastructure** | Adaptadores concretos: SQLAlchemy, Redis, Cognito, S3 | Lógica de negocio |
| **Interfaces** | Routers FastAPI, schemas Pydantic, CLI | Lógica de negocio, acceso directo a DB |

## 2. Estructura de carpetas del backend

```
backend/
├── app/
│   ├── domain/
│   │   ├── entities/
│   │   │   ├── student.py
│   │   │   ├── course.py
│   │   │   ├── course_offering.py
│   │   │   ├── enrollment.py
│   │   │   └── enrollment_period.py
│   │   ├── value_objects/
│   │   │   ├── student_code.py
│   │   │   ├── course_code.py
│   │   │   └── schedule_block.py
│   │   ├── exceptions/
│   │   │   ├── capacity_exceeded.py
│   │   │   ├── prerequisites_not_met.py
│   │   │   ├── schedule_conflict.py
│   │   │   └── already_enrolled.py
│   │   └── services/
│   │       ├── prerequisite_validator.py
│   │       └── schedule_conflict_detector.py
│   │
│   ├── application/
│   │   ├── use_cases/
│   │   │   ├── auth/
│   │   │   │   ├── authenticate_user.py
│   │   │   │   └── refresh_token.py
│   │   │   ├── catalog/
│   │   │   │   ├── list_courses.py
│   │   │   │   ├── get_course_offerings.py
│   │   │   │   └── get_offering_detail.py
│   │   │   ├── enrollment/
│   │   │   │   ├── enroll_student.py       # el más crítico
│   │   │   │   ├── cancel_enrollment.py
│   │   │   │   └── get_student_schedule.py
│   │   │   └── admin/
│   │   │       ├── create_enrollment_period.py
│   │   │       ├── create_course_offering.py
│   │   │       └── generate_enrollment_report.py
│   │   ├── ports/
│   │   │   ├── repositories/
│   │   │   │   ├── student_repository.py
│   │   │   │   ├── course_repository.py
│   │   │   │   ├── offering_repository.py
│   │   │   │   ├── enrollment_repository.py
│   │   │   │   └── period_repository.py
│   │   │   ├── cache_service.py
│   │   │   ├── auth_service.py
│   │   │   ├── notification_service.py
│   │   │   └── unit_of_work.py
│   │   └── dtos/
│   │       ├── enrollment_dto.py
│   │       └── course_dto.py
│   │
│   ├── infrastructure/
│   │   ├── persistence/
│   │   │   ├── sqlalchemy/
│   │   │   │   ├── models/          # modelos ORM (Table declarations)
│   │   │   │   ├── repositories/    # implementaciones de puertos
│   │   │   │   ├── unit_of_work.py
│   │   │   │   └── session.py
│   │   ├── cache/
│   │   │   └── redis_cache_service.py
│   │   ├── auth/
│   │   │   └── jwt_auth_service.py
│   │   ├── notifications/
│   │   │   └── smtp_notification_service.py
│   │   └── config/
│   │       └── settings.py
│   │
│   ├── interfaces/
│   │   └── api/
│   │       ├── routers/
│   │       │   ├── auth.py
│   │       │   ├── students.py
│   │       │   ├── courses.py
│   │       │   ├── enrollments.py
│   │       │   ├── periods.py
│   │       │   └── admin.py
│   │       ├── schemas/
│   │       │   ├── auth_schemas.py
│   │       │   ├── student_schemas.py
│   │       │   ├── enrollment_schemas.py
│   │       │   └── error_schemas.py
│   │       ├── dependencies/
│   │       │   ├── auth.py          # get_current_user, require_admin
│   │       │   └── di.py            # inyección de dependencias
│   │       └── main.py              # entrypoint FastAPI
│   │
│   └── __init__.py
│
├── alembic/                    # migraciones
├── tests/
│   ├── unit/                   # tests de dominio y casos de uso (rápidos)
│   ├── integration/            # tests con DB real (Testcontainers)
│   └── e2e/                    # tests de la API completa
├── pyproject.toml
├── Dockerfile
└── README.md
```

**Cada archivo tiene un propósito claro derivado del dominio.** No hay carpetas ni archivos de relleno.

## 3. Diagrama de paquetes

```
┌──────────────────────────────────────────────────────────┐
│                    interfaces.api                         │
│     [routers, schemas, dependencies, main]                │
└──────────────────┬───────────────────────────────────────┘
                   │ usa
                   ▼
┌──────────────────────────────────────────────────────────┐
│                application.use_cases                      │
│  [enroll_student, list_courses, cancel_enrollment, ...]  │
└──────┬─────────────────────────┬─────────────────────────┘
       │ orquesta                │ depende de (interfaz)
       ▼                         ▼
┌────────────────────┐   ┌─────────────────────────┐
│      domain        │   │  application.ports      │
│  [entities,        │   │  [repositories,          │
│   value_objects,   │   │   cache_service,         │
│   services,        │   │   auth_service,          │
│   exceptions]      │   │   unit_of_work]          │
└────────────────────┘   └────────────┬────────────┘
                                       │ implementa
                                       ▼
                        ┌────────────────────────────┐
                        │      infrastructure         │
                        │  [sqlalchemy_repos,         │
                        │   redis_cache,              │
                        │   jwt_auth,                 │
                        │   smtp_notifications]       │
                        └────────────────────────────┘
```

## 4. Diagrama de clases del caso de uso crítico

El caso de uso **EnrollStudent** es el más importante del sistema. Muestra cómo colaboran las capas.

```
┌────────────────────────────┐         ┌────────────────────────────┐
│  EnrollmentRouter          │         │  EnrollmentRequestSchema   │
│  (interfaces.api)          │◄────────┤  (Pydantic)                │
│                            │         └────────────────────────────┘
│  + POST /enrollments()     │
└──────────┬─────────────────┘
           │ inyecta y llama
           ▼
┌───────────────────────────────────────────────────────────────┐
│  EnrollStudentUseCase   (application.use_cases.enrollment)    │
│                                                                │
│  - student_repo: StudentRepository                             │
│  - offering_repo: OfferingRepository                           │
│  - enrollment_repo: EnrollmentRepository                       │
│  - period_repo: PeriodRepository                               │
│  - prerequisite_validator: PrerequisiteValidator               │
│  - schedule_detector: ScheduleConflictDetector                 │
│  - uow: UnitOfWork                                             │
│  - cache: CacheService                                         │
│                                                                │
│  + execute(student_id, offering_id) -> EnrollmentDTO           │
│      1. Validar período activo                                 │
│      2. Cargar student, offering, historial                    │
│      3. Validar prerrequisitos (domain service)                │
│      4. Validar no-choque de horario (domain service)          │
│      5. Validar no-inscrito-ya                                 │
│      6. Transacción: descontar cupo (bloqueo optimista)        │
│      7. Crear enrollment                                       │
│      8. Invalidar caché del offering                           │
│      9. Retornar EnrollmentDTO                                 │
└───────────┬───────────────────────────┬────────────────────────┘
            │ usa                        │ usa
            ▼                            ▼
┌───────────────────────┐    ┌───────────────────────────────┐
│  Enrollment           │    │  CourseOffering               │
│  (domain.entities)    │    │  (domain.entities)            │
│                       │    │                                │
│  - id                 │    │  - id                          │
│  - student_id         │    │  - total_capacity              │
│  - offering_id        │    │  - enrolled_count              │
│  - status             │    │  - version (optim. lock)       │
│  - enrolled_at        │    │                                │
│                       │    │  + can_accept_enrollment()     │
│  + cancel()           │    │  + reserve_slot() -> raises    │
│  + is_active()        │    │       CapacityExceeded         │
└───────────────────────┘    │  + release_slot()              │
                             └───────────────────────────────┘
```

**Puntos importantes de este diseño:**

1. El router **no contiene lógica de negocio.** Solo valida el request, invoca el caso de uso y traduce excepciones a códigos HTTP.
2. El caso de uso **orquesta pero no decide.** Las validaciones son servicios del dominio; el descuento de cupo es un método de la entidad `CourseOffering`.
3. La entidad `CourseOffering` **encapsula su propia invariante:** el método `reserve_slot()` verifica capacidad y lanza excepción si no es posible. La regla no está dispersa.
4. Las dependencias externas (repos, caché, uow) se **inyectan como interfaces**, no como implementaciones concretas.

## 5. Aplicación de los principios SOLID

Cada principio SOLID se aplica de forma concreta en este proyecto, no como decoración.

### S — Single Responsibility Principle

Cada clase tiene una y solo una razón para cambiar.

**Ejemplo aplicado:** el caso de uso de inscripción no valida prerrequisitos ni detecta conflictos de horario directamente. Delega:

- `PrerequisiteValidator` — cambia si cambia la regla de prerrequisitos.
- `ScheduleConflictDetector` — cambia si cambia la regla de choque de horarios.
- `EnrollStudentUseCase` — cambia si cambia el flujo de orquestación.
- `EnrollmentRepository` — cambia si cambia la forma de persistir.

**Antipatrón evitado:** una clase `EnrollmentService` de 800 líneas que valida, persiste, notifica y genera PDFs. Sería imposible de mantener y de probar.

### O — Open/Closed Principle

Las clases están abiertas a extensión, cerradas a modificación.

**Ejemplo aplicado:** el servicio de notificación se define como puerto (`NotificationService`). Hoy hay una implementación con SMTP. Si mañana se añade notificación por SMS, se crea `TwilioNotificationService` implementando el mismo puerto, y el código de negocio no cambia.

```python
# Puerto (abstracción)
class NotificationService(ABC):
    @abstractmethod
    def notify_enrollment(self, student: Student, enrollment: Enrollment) -> None: ...

# Extensión sin modificación
class SMTPNotificationService(NotificationService): ...
class TwilioNotificationService(NotificationService): ...
```

### L — Liskov Substitution Principle

Cualquier implementación de un puerto debe ser sustituible sin romper el sistema.

**Ejemplo aplicado:** los repositorios definen un contrato preciso. `SQLAlchemyStudentRepository` y `InMemoryStudentRepository` (usado en tests unitarios) son 100% intercambiables. Si un test pasa con el segundo pero falla con el primero, es un bug del adaptador SQL, no del contrato.

### I — Interface Segregation Principle

Interfaces pequeñas y específicas en vez de una gigante con métodos que no todos usan.

**Ejemplo aplicado:** en lugar de un único `EnrollmentRepository` con 15 métodos (find, save, count, exists, listByStudent, listByOffering, listActive, listCancelled, etc.), se separan responsabilidades:

```python
class EnrollmentReader(ABC):
    def find_by_id(self, id: UUID) -> Enrollment | None: ...
    def find_active_by_student(self, student_id: UUID) -> list[Enrollment]: ...

class EnrollmentWriter(ABC):
    def save(self, enrollment: Enrollment) -> None: ...
    def cancel(self, id: UUID) -> None: ...

class EnrollmentRepository(EnrollmentReader, EnrollmentWriter):
    pass
```

Un caso de uso de solo lectura (ej. generar reporte) depende únicamente de `EnrollmentReader`, no del contrato completo.

### D — Dependency Inversion Principle

El dominio no depende de infraestructura; ambos dependen de abstracciones.

**Ejemplo aplicado:** en `application/ports/repositories/enrollment_repository.py` se define la interfaz. La implementación vive en `infrastructure/persistence/sqlalchemy/repositories/`. El caso de uso recibe la interfaz vía constructor:

```python
class EnrollStudentUseCase:
    def __init__(
        self,
        enrollment_repo: EnrollmentRepository,   # abstracción
        offering_repo: OfferingRepository,       # abstracción
        uow: UnitOfWork,                          # abstracción
    ):
        ...
```

La inyección concreta se resuelve en el contenedor de dependencias de FastAPI (`interfaces/api/dependencies/di.py`). El dominio nunca importa nada de `infrastructure`.

## 6. Otras convenciones arquitectónicas

### Unit of Work

Las operaciones que tocan múltiples tablas (ej. crear un enrollment y actualizar el cupo del offering) se ejecutan bajo un `UnitOfWork` que garantiza atomicidad transaccional:

```python
with uow:
    offering = offering_repo.get_for_update(offering_id)
    offering.reserve_slot()
    enrollment = Enrollment.create(student, offering)
    enrollment_repo.save(enrollment)
    uow.commit()
```

Si algo falla dentro del `with`, todo se revierte.

### DTOs vs Entidades

- Las **entidades** del dominio (`Enrollment`, `CourseOffering`) contienen lógica y son ricas en comportamiento. No se serializan a JSON directamente.
- Los **DTOs** (`EnrollmentDTO`) son estructuras planas para transporte entre capas y para respuestas de la API. Se construyen a partir de entidades.
- Los **schemas Pydantic** (`EnrollmentResponseSchema`) validan y serializan en la capa de API. No se usan en la capa de dominio.

### Manejo de errores

- Errores del dominio → excepciones específicas (`CapacityExceededException`, `PrerequisitesNotMetException`).
- El router traduce excepciones a códigos HTTP mediante un handler centralizado.
- Nunca se lanza `Exception` genérica.

### Ausencias intencionales

- **No hay repositorios genéricos** tipo `IRepository<T>`. Cada agregado tiene su repositorio con métodos específicos.
- **No hay ORM en la capa de dominio.** Los modelos SQLAlchemy viven en `infrastructure/persistence/sqlalchemy/models/`, y los repositorios mapean entre modelos ORM y entidades del dominio.
- **No hay servicios de aplicación anémicos.** Si un caso de uso solo llama a un método del repositorio, probablemente no necesita existir todavía (YAGNI).

## 7. Cómo se refleja esto en las pruebas

La arquitectura habilita tres niveles de tests:

| Nivel | Qué prueba | Velocidad | Herramientas |
|---|---|---|---|
| **Unit** | Entidades del dominio y casos de uso con dobles de test | milisegundos | pytest, pytest-mock |
| **Integration** | Adaptadores contra infraestructura real | segundos | pytest + Testcontainers (PostgreSQL, Redis) |
| **E2E** | API completa levantada | decenas de segundos | pytest + httpx contra la app real |

El objetivo es tener muchas pruebas unitarias (rápidas, aisladas) y pocas pruebas E2E (lentas, integrales). La pirámide de tests se sostiene gracias a la separación de capas.
