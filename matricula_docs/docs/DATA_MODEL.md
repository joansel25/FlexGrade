# Modelo de datos

Este documento describe el modelo de datos del Sistema de Matrícula Académica: las entidades del dominio, sus relaciones y el esquema SQL de PostgreSQL. Cada entidad tiene un propósito claro derivado de un caso de uso real; no hay tablas ni columnas de relleno.

## 1. Entidades del dominio

### Contexto

El dominio de matrícula académica gira alrededor de tres ideas centrales:

1. Un **estudiante** pertenece a un **programa** académico.
2. Un **programa** tiene un plan de estudios compuesto por **materias**, y los requisitos entre ellas —prerrequisitos y correquisitos— pertenecen a ese plan, no al catálogo.
3. Cada semestre, una materia se ofrece en uno o más **grupos** (con un profesor, un horario y un cupo), y los estudiantes se **inscriben** a esos grupos durante una ventana de tiempo llamada **período de matrícula**.

### Diagrama de entidades (texto)

```
                                    ┌──────────────────┐
                                    │      User        │
                                    │  (autenticación) │
                                    └────────┬─────────┘
                                             │
                             ┌───────────────┴───────────────┐
                             │                               │
                    ┌────────▼─────────┐          ┌──────────▼─────────┐
                    │     Student      │          │   Administrator    │
                    └────────┬─────────┘          └────────────────────┘
                             │ n:1
                             │
                    ┌────────▼─────────┐          ┌────────────────────┐
                    │     Program      │◄─────────┤       Course       │
                    │  (Ing. Sistemas) │  n:m     │  ("Cálculo I")     │
                    └──────────────────┘          └─────────┬──────────┘
                                                            │ 1:n
                                                            │
                                                  ┌─────────▼──────────┐
                                                  │  CourseOffering    │
                                                  │  ("Cálculo I - 01")│
                                                  └──┬──────────────┬──┘
                                                     │ 1:n          │ n:1
                                                     │              │
                                          ┌──────────▼─────┐  ┌────▼──────┐
                                          │ ScheduleBlock  │  │ Professor │
                                          │  (Lun 8-10)    │  └───────────┘
                                          └────────────────┘

┌────────────────────┐          ┌─────────────────────┐          ┌────────────────┐
│  EnrollmentPeriod  │◄─────────┤    Enrollment       ├─────────►│    Student     │
│  ("2025-2 v1")     │  n:1     │   (una inscripción) │  n:1     └────────────────┘
└────────────────────┘          └──────────┬──────────┘
                                           │ n:1
                                           │
                                ┌──────────▼──────────┐
                                │   CourseOffering    │
                                └─────────────────────┘

┌──────────────────┐
│ Prerequisite     │  (autorreferencia sobre Course)
│ course_id ────►  │
│ requires_id ─►   │
└──────────────────┘

┌──────────────────┐
│ AcademicHistory  │  (materias ya cursadas y aprobadas por el estudiante)
└──────────────────┘
```

### Descripción de cada entidad

| Entidad | Propósito | Notas |
|---|---|---|
| **User** | Cuenta de autenticación (email + credenciales) | Base común para estudiantes y administradores |
| **Student** | Perfil académico del estudiante | Vincula a un User con un Program y datos académicos |
| **Administrator** | Perfil administrativo | Vincula a un User con permisos de gestión |
| **Program** | Programa académico ofrecido por la institución | Ej: "Ingeniería de Sistemas", "Derecho" |
| **Course** | Materia del plan de estudios | Independiente del semestre y del grupo |
| **CourseRequirement** | Requisito entre dos materias DENTRO de un plan de estudios | Un Course puede exigir aprobar otro antes (`PREREQUISITE`) o cursarlo a la vez (`COREQUISITE`) |
| **Professor** | Profesor que dicta grupos | Puede dictar múltiples grupos por semestre |
| **CourseOffering** | Oferta concreta de una materia en un semestre | "Cálculo I - Grupo 01 - Semestre 2025-2" |
| **ScheduleBlock** | Bloque de horario de un grupo | Un grupo puede tener varios bloques (Lun 8-10 y Mié 8-10) |
| **EnrollmentPeriod** | Ventana temporal en la que se pueden inscribir materias | Ej: "2025-2 primera vuelta: 15-17 nov 2025" |
| **Enrollment** | Inscripción de un estudiante en un grupo | Estados: ENROLLED, CANCELLED, WAITLISTED |
| **AcademicHistory** | Registro histórico de materias cursadas y aprobadas | Base para validar prerrequisitos |

## 2. Esquema SQL (PostgreSQL 16)

### Convenciones

- Nombres de tablas en **snake_case plural** (`students`, `course_offerings`).
- Claves primarias como `id` tipo `UUID` con `gen_random_uuid()` por defecto.
- Timestamps `created_at` y `updated_at` en todas las tablas transaccionales.
- Restricciones referenciales explícitas con `ON DELETE` según corresponda.
- Índices en columnas usadas para búsqueda y en claves foráneas de alta frecuencia.
- Índices con prefijo `ix_`, siguiendo la `naming_convention` del `MetaData` de SQLAlchemy y lo que genera Alembic con `--autogenerate`.
- No se declaran índices sobre columnas ya cubiertas por un `UNIQUE`: PostgreSQL crea un índice B-tree al imponer la restricción, y duplicarlo solo añade coste de escritura y de mantenimiento.

### DDL completo

```sql
-- =========================================================
-- Extensiones
-- =========================================================
CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- para gen_random_uuid()

-- =========================================================
-- Usuarios y perfiles
-- =========================================================
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('STUDENT', 'ADMIN')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE programs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(20) NOT NULL UNIQUE,        -- "ISIS", "DER"
    name VARCHAR(150) NOT NULL,              -- "Ingeniería de Sistemas"
    total_semesters INTEGER NOT NULL CHECK (total_semesters > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE students (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    student_code VARCHAR(20) NOT NULL UNIQUE,   -- código institucional
    program_id UUID NOT NULL REFERENCES programs(id),
    current_semester INTEGER NOT NULL CHECK (current_semester >= 1),
    full_name VARCHAR(200) NOT NULL,
    enrollment_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_students_program ON students(program_id);

CREATE TABLE administrators (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    full_name VARCHAR(200) NOT NULL,
    department VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =========================================================
-- Catálogo académico
-- =========================================================
CREATE TABLE professors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name VARCHAR(200) NOT NULL,
    email VARCHAR(255) UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE courses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(20) NOT NULL UNIQUE,        -- "MAT101"
    name VARCHAR(150) NOT NULL,              -- "Cálculo I"
    credits INTEGER NOT NULL CHECK (credits > 0),
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE program_courses (
    program_id UUID NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    suggested_semester INTEGER NOT NULL CHECK (suggested_semester >= 1),
    is_mandatory BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (program_id, course_id)
);

-- Los requisitos pertenecen al PLAN DE ESTUDIOS, no al catálogo. Sustituyó a
-- `course_prerequisites` en la migración `0007`; la razón está en la sección «Requisitos
-- académicos» de este documento.
CREATE TABLE program_course_requirements (
    program_id UUID NOT NULL,
    course_id UUID NOT NULL,
    required_course_id UUID NOT NULL,
    requirement_type VARCHAR(20) NOT NULL
        CHECK (requirement_type IN ('PREREQUISITE', 'COREQUISITE')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (program_id, course_id, required_course_id),
    CHECK (course_id <> required_course_id),
    -- Claves foráneas COMPUESTAS contra el plan: hacen imposible declarar un requisito sobre
    -- una materia que no pertenece a esa carrera.
    CONSTRAINT fk_pcr_course_in_plan FOREIGN KEY (program_id, course_id)
        REFERENCES program_courses(program_id, course_id) ON DELETE CASCADE,
    CONSTRAINT fk_pcr_required_course_in_plan FOREIGN KEY (program_id, required_course_id)
        REFERENCES program_courses(program_id, course_id) ON DELETE CASCADE
);

-- =========================================================
-- Ofertas del semestre
-- =========================================================
CREATE TABLE enrollment_periods (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(20) NOT NULL UNIQUE,        -- "2025-2-V1"
    academic_period VARCHAR(20) NOT NULL,    -- "2025-2"
    name VARCHAR(150) NOT NULL,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (ends_at > starts_at)
);

-- Parcial y UNICO: acelera "dame el periodo activo" y a la vez impide que existan dos
-- periodos activos a la vez. Las filas inactivas quedan fuera del indice, asi que puede
-- haber tantos periodos historicos como haga falta. Ver "Un solo periodo activo" mas abajo.
CREATE UNIQUE INDEX ix_enrollment_periods_active ON enrollment_periods(is_active) WHERE is_active = TRUE;

CREATE TABLE course_offerings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    enrollment_period_id UUID NOT NULL REFERENCES enrollment_periods(id) ON DELETE CASCADE,
    course_id UUID NOT NULL REFERENCES courses(id),
    professor_id UUID REFERENCES professors(id),
    group_number VARCHAR(10) NOT NULL,       -- "01", "02"
    total_capacity INTEGER NOT NULL CHECK (total_capacity > 0),
    enrolled_count INTEGER NOT NULL DEFAULT 0 CHECK (enrolled_count >= 0),
    version INTEGER NOT NULL DEFAULT 0,       -- para bloqueo optimista
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (enrollment_period_id, course_id, group_number),
    CHECK (enrolled_count <= total_capacity)
);

CREATE INDEX ix_offerings_period ON course_offerings(enrollment_period_id);
CREATE INDEX ix_offerings_course ON course_offerings(course_id);

CREATE TABLE schedule_blocks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_offering_id UUID NOT NULL REFERENCES course_offerings(id) ON DELETE CASCADE,
    day_of_week SMALLINT NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),  -- 1=Lun, 7=Dom
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    classroom VARCHAR(50),
    CHECK (end_time > start_time)
);

CREATE INDEX ix_schedule_offering ON schedule_blocks(course_offering_id);

-- =========================================================
-- Inscripciones (transaccional crítico)
-- =========================================================
CREATE TABLE enrollments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id UUID NOT NULL REFERENCES students(id),
    course_offering_id UUID NOT NULL REFERENCES course_offerings(id),
    enrollment_period_id UUID NOT NULL REFERENCES enrollment_periods(id),
    status VARCHAR(20) NOT NULL DEFAULT 'ENROLLED'
        CHECK (status IN ('ENROLLED', 'CANCELLED', 'WAITLISTED')),
    enrolled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cancelled_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (student_id, course_offering_id, enrollment_period_id)
);

CREATE INDEX ix_enrollments_offering ON enrollments(course_offering_id);
CREATE INDEX ix_enrollments_period ON enrollments(enrollment_period_id);
-- Parcial sobre student_id, NO sobre status: ver "Indices de las inscripciones" mas abajo.
CREATE INDEX ix_enrollments_active ON enrollments(student_id) WHERE status = 'ENROLLED';

-- =========================================================
-- Historial académico (para validación de prerrequisitos)
-- =========================================================
CREATE TABLE academic_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    course_id UUID NOT NULL REFERENCES courses(id),
    academic_period VARCHAR(20) NOT NULL,       -- "2024-2"
    final_grade NUMERIC(3, 2) CHECK (final_grade BETWEEN 0.0 AND 5.0),
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('APPROVED', 'FAILED', 'WITHDRAWN')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (student_id, course_id, academic_period)
);

-- ix_history_student NO se crea: seria un duplicado exacto del prefijo del indice que
-- PostgreSQL genera para uq_academic_history_student_course_period.
CREATE INDEX ix_history_student_status ON academic_history(student_id, status);
```

## 3. Notas de diseño

### Concurrencia en el descuento de cupos

El campo `course_offerings.enrolled_count` se actualiza durante la inscripción en un contexto de alta concurrencia. Para evitar sobrecupo se combinan **tres** defensas en capas, y ninguna sustituye a las otras:

1. **La invariante en la entidad.** `CourseOffering.reserve_slot()` comprueba la capacidad sobre el grupo recién leído y lanza `CapacityExceededError` si está lleno. Es la regla del dominio, se prueba en milisegundos sin base de datos, y descarta el caso obvio sin gastar una escritura.
2. **Escritura condicionada y atómica.** El descuento se hace en una sola sentencia:
   ```sql
   UPDATE course_offerings
   SET enrolled_count = enrolled_count + 1, version = version + 1
   WHERE id = :id AND enrolled_count < total_capacity
   ```
   No hay lectura previa, así que no existe ventana entre comprobar y escribir. PostgreSQL serializa el acceso a la fila, de modo que cada transacción evalúa la condición contra el valor que la anterior acaba de dejar. Si afecta a cero filas, el grupo se llenó: la aplicación responde `409` sin reintentar.
3. **Restricción CHECK** (`enrolled_count <= total_capacity`) como red de seguridad final. Si las dos anteriores fallaran por un defecto de código, PostgreSQL rechaza la fila.

#### Por qué no se usa `WHERE version = ?` con reintentos

El diseño original de este documento proponía bloqueo optimista por versión con reintentos acotados. **Se implementó tal cual y se midió con hilos reales contra PostgreSQL, y no escala.**

El motivo es estructural: con N transacciones compitiendo por la misma fila, PostgreSQL las serializa y solo una gana por ronda; las demás encuentran la versión cambiada y reintentan. Harían falta hasta N reintentos, es decir, trabajo cuadrático. Con un límite razonable de reintentos el efecto medido fue este:

| Escenario | Con `WHERE version = ?` | Con `WHERE enrolled_count < total_capacity` |
|---|---|---|
| 100 concurrentes, último cupo | 1 entra ✓ | 1 entra ✓ |
| 100 concurrentes, 50 cupos | menos de 50 entran ✗ | 50 entran ✓ |
| 40 concurrentes, 100 cupos | **10 de 40 entran** ✗ | 40 entran ✓ |
| 200 concurrentes, 100 cupos | — | 100 entran, en 1,7 s ✓ |

La fila crítica es la tercera: a 30 personas se les rechazaba un cupo que existía. Condicionar por `enrolled_count < total_capacity` elimina el problema de raíz —cada transacción reevalúa la condición real— y hace innecesario reintentar.

**`version` se conserva y se sigue incrementando** en esa misma sentencia. Mantiene su valor como marca de modificación y para el bloqueo optimista de otras operaciones sobre el grupo, como ajustar la capacidad desde administración (Fase 4), donde los conflictos sí son raros y el mecanismo por versión es el adecuado.

La garantía la sostienen los tests de `backend/tests/integration/test_enrollment_concurrency.py`, que corren con hilos reales y una barrera de sincronización para provocar la contención en vez de suponerla.

### Caché de consultas frecuentes

Las consultas de catálogo (listado de materias, disponibilidad de grupos) son las de mayor frecuencia durante el pico. Se cachean en Redis con TTL corto (30-60 segundos), lo suficiente para absorber miles de consultas idénticas sin golpear la base de datos.

**No se cachea** la operación de inscripción ni la disponibilidad exacta en el momento del descuento: siempre consultan directo a PostgreSQL para garantizar consistencia.

### Un solo período activo

`enrollment_periods.is_active` lleva un índice **parcial y único** (`WHERE is_active = TRUE`), no un índice corriente. La estructura hace dos trabajos a la vez:

1. **Rendimiento.** «Dame el período activo» es la consulta más frecuente del sistema: la ejecutan el catálogo de grupos y cada intento de inscripción. Indexar solo las filas activas cuesta unos pocos bytes; un índice sobre toda la columna acabaría apuntando a millones de filas inactivas sin resolver nada, porque la columna solo tiene dos valores distintos.

2. **Corrección.** Impide que existan dos períodos activos simultáneos. Es lo que permite que `PeriodRepository.find_active()` devuelva un único período sin ambigüedad: con dos filas activas, la base devolvería una u otra de forma arbitraria y el catálogo mostraría la oferta del semestre equivocado. Dejar esa garantía en manos del endpoint de activación sería confiar en que ningún otro camino de escritura —un script de migración de datos, una corrección manual, un endpoint futuro— se equivoque nunca.

Activar un período nuevo exige, por tanto, desactivar el anterior en la misma transacción. Es una restricción deseable: obliga a que el cambio de ventana sea una operación atómica y explícita, no un efecto colateral.

### Índices de las inscripciones

Dos decisiones sobre las tablas de la Fase 3 que se apartan de lo que parecería natural, y conviene dejar razonadas:

**`ix_enrollments_active` va sobre `student_id`, no sobre `status`.** Un índice sobre `status` filtrado además por `WHERE status = 'ENROLLED'` contendría con el tiempo millones de filas **con la misma clave**: no discrimina nada y PostgreSQL apenas lo usaría. La columna que discrimina es `student_id`, porque la consulta que de verdad corre en cada intento de inscripción es «qué tiene inscrito ahora esta persona» —la que alimenta la detección de choque de horarios y de doble inscripción—. El filtro parcial sí se mantiene: las canceladas se acumulan semestre a semestre y nunca interesan para esa pregunta.

**`ix_history_student` no se crea.** Es idéntico al prefijo del índice que PostgreSQL genera automáticamente para la restricción `uq_academic_history_student_course_period`, así que sería un duplicado exacto: coste de escritura y de espacio sin ninguna ganancia en lectura. Es el mismo defecto que corrigió la migración `0003` para `users` y `students`. `ix_history_student_status` sí se crea, porque esa restricción no puede resolver un filtro por `(student_id, status)` más allá del primer campo.

### Requisitos académicos

**Un requisito no une dos materias: une dos materias dentro de un plan de estudios.** El modelo original lo trataba como una relación autoreferente sobre `courses`, y esa forma afirmaba que `MAT102` exige `MAT101` en toda la institución. Deja de ser cierto en cuanto una materia entra en dos planes: la misma materia puede ser obligatoria con prerrequisito en Ingeniería y electiva libre en Administración, y en una tabla sin programa una de las dos verdades tenía que estar mal. Es el mismo motivo por el que `suggested_semester` e `is_mandatory` viven en `program_courses` y no en `courses`.

Los dos tipos se validan contra fuentes distintas, y de ahí que sean un tipo y no un booleano:

| Tipo | Contra qué se valida | Cuándo puede cumplirse |
|---|---|---|
| `PREREQUISITE` | `academic_history` con `status = 'APPROVED'` | En un semestre anterior; hoy no hay nada que hacer |
| `COREQUISITE` | Las inscripciones ACTIVAS del período vigente, o el historial aprobado | Ahora mismo, inscribiendo la otra materia |

**El correquisito mutuo y el bloqueo circular.** Un prerrequisito circular es un error de datos; un correquisito circular es lo normal —la teoría y su laboratorio se cursan juntos— y tiene que funcionar. Si `A` exige `B` y `B` exige `A`, y cada una exigiera que la otra estuviera inscrita *antes*, la primera de las dos fallaría siempre y el bloque quedaría fuera de la matrícula por cualquier camino. La salida es validar el **conjunto**: las materias unidas por correquisitos recíprocos forman un bloque que se cursa entero y cualquiera de ellas puede entrar primero. El repositorio identifica esos pares con un autojoin (`find_mutual_corequisites`) y el validador no les exige estar ya inscritas.

La contrapartida está asumida: entre la primera inscripción del bloque y la segunda, la matrícula queda incompleta. La alternativa era un endpoint de inscripción múltiple que aceptara el bloque en una transacción, y se descartó porque cambia el contrato de la operación más crítica del sistema. Ese estado intermedio se permite, pero **no se esconde**: `GET /students/me/enrollments` devuelve `pending_corequisites` por materia, calculado con la misma regla que decide si la inscripción se acepta.

**La regla vale en las dos direcciones.** Cancelar también la respeta, y omitirlo sería dejar una puerta trasera al estado que inscribir rechaza. Una dependencia en un solo sentido bloquea la cancelación con `COREQUISITE_DEPENDENCY` hasta que se cancele antes la materia que depende; una dependencia mutua cancela el bloque entero, porque rechazarla dejaría las dos imposibles de abandonar. La consulta que lo sostiene es la inversa —«qué materias exigen a esta»— y filtra por `(program_id, required_course_id)`, que no es prefijo de la clave primaria: por eso la migración `0008` le da índice propio. Sin él, PostgreSQL recorrería la tabla entera dentro de la transacción que libera un cupo mientras otras personas compiten por él.

### Espacios físicos

**El aula dejó de ser un texto.** Hasta la iteración 7.1 vivía como `schedule_blocks.classroom`, una columna de texto libre. Con eso, `A-201`, `A201` y `Aula A-201` eran tres aulas distintas para la base de datos y la misma para las personas, de lo que salen dos problemas que no se arreglan validando la cadena: no había forma fiable de responder «¿qué hay en A-201 el martes a las 10?», y por tanto tampoco de impedir que dos grupos reservaran el mismo salón a la misma hora. **Un texto no puede estar ocupado; una fila sí.**

La migración `0009` crea `spaces` y sustituye la columna por `schedule_blocks.space_id`. El traslado convierte cada texto distinto en un espacio —normalizando con `TRIM` y mayúsculas, para no arrastrar a la tabla nueva el problema que viene a resolver— y reengancha cada franja al suyo ANTES de borrar la columna. Sobre los datos de desarrollo produjo 21 espacios y dejó **cero franjas sin aula**: no se perdió ninguna asignación.

Dos decisiones del modelo que conviene no revisar sin motivo:

- **`capacity` admite nulos.** En la cadena «A-201» no hay ningún número de sillas, así que los espacios creados por el traslado no traían aforo. Poner `NOT NULL` habría obligado a inventar una cifra, y una capacidad inventada no la revisa nadie: se convierte en el dato contra el que la 7.2 valida el aforo. El `CHECK` exige que, cuando exista, sea positiva. La entidad refleja lo mismo: `Space.fits()` devuelve `None` —ni `True` ni `False`— cuando el aforo se desconoce.
- **`ON DELETE SET NULL` y no `CASCADE`.** Retirar un espacio del inventario no debe borrar la clase; debe dejarla sin aula asignada, que es lo que ha ocurrido.

`ix_schedule_space` sobre `(space_id, day_of_week)` es PARCIAL, filtrado por `space_id IS NOT NULL`: las franjas sin aula no responden nada a la pregunta «qué hay reservado aquí», y con el tiempo serían la mayoría de un índice que nunca las mira. Es el que sostendrá la detección de doble reserva de la 7.2.

### Doble reserva de un espacio

**Dos defensas, igual que con el sobrecupo, y ninguna sustituye a la otra.** `SpaceConflictDetector` comprueba en el caso de uso que el aula esté libre y que el grupo quepa, y responde con el día, la hora y el grupo que la ocupa. La garantía la da PostgreSQL con una restricción de exclusión `GiST` (migración `0010`):

```sql
EXCLUDE USING gist (
    space_id WITH =, enrollment_period_id WITH =, day_of_week WITH =,
    tsrange(DATE '2000-01-01' + start_time, DATE '2000-01-01' + end_time, '[)') WITH &&
) WHERE (space_id IS NOT NULL)
```

Sin la restricción, dos peticiones simultáneas comprueban a la vez que el aula está libre y la reservan las dos: ninguna validación en la aplicación cierra esa carrera. Sin la validación, esa carrera perdida le llega a una persona como un error de integridad y un 500.

Cuatro decisiones dentro de esa restricción:

- **`enrollment_period_id` está desnormalizado en `schedule_blocks`.** Una restricción de exclusión solo mira columnas de su tabla, y sin el período prohibiría reutilizar un aula el semestre siguiente a la misma hora, que es lo normal. La copia no queda a merced del código: la clave foránea es compuesta sobre `(course_offering_id, enrollment_period_id)`, el mismo recurso que usa `program_course_requirements`.
- **`tsrange` sobre una fecha fija y no un tipo `timerange` propio.** PostgreSQL no trae rangos sobre `time`, y un tipo a medida complica el `downgrade` sin ganar nada. La fecha da igual mientras sea la misma para todas las filas: `day_of_week` ya separa los días.
- **`[)` y no `[]`.** Una clase que termina a las 10:00 y otra que empieza a las 10:00 son consecutivas. Es la misma regla que aplica `ScheduleBlock.overlaps`, y si las dos no coincidieran una aceptaría lo que la otra rechaza.
- **Parcial sobre `space_id IS NOT NULL`.** Una franja sin aula no ocupa nada; sin el filtro, todas las clases sin espacio del mismo día chocarían entre sí y publicar el horario antes de repartir aulas sería imposible.

**La migración libera las dobles reservas que ya existían.** No es hipotético: mientras el aula fue texto libre nada las impidió, así que cualquier base real llega con conflictos y `ADD CONSTRAINT` los rechaza en bloque. Sobre los datos de desarrollo liberó 18 franjas. Se resuelve dejando **sin aula** a la que llegó después, nunca borrándola: la clase existe y su horario es correcto; lo que está mal es dónde se dijo que era.

**El aforo solo bloquea cuando se conoce.** `Space.fits()` devuelve `None` para los espacios sin aforo medido, y tratar ese «no sé» como un «no cabe» inutilizaría aulas válidas por una laguna del inventario.

### Auditoría temporal

No todas las tablas necesitan el mismo rastro temporal. La distinción sigue el ciclo de vida real de cada fila:

| Tipo de tabla | Tablas | Columnas |
|---|---|---|
| Catálogo y registro histórico (se crean y rara vez cambian) | `programs`, `courses`, `professors`, `students`, `administrators`, `schedule_blocks`, `academic_history`, `enrollment_periods` | `created_at` |
| Transaccional (mutan después de creadas) | `users`, `course_offerings`, `enrollments` | `created_at` + `updated_at` |

Las tablas de catálogo se corrigen mediante migraciones o tareas administrativas puntuales, no como parte del flujo normal del sistema; un `updated_at` ahí sería una columna que nadie consulta. Las transaccionales sí cambian en operación normal: `enrolled_count` y `version` en `course_offerings` durante cada inscripción, `status` y `cancelled_at` en `enrollments` al cancelar, y las credenciales o el estado activo en `users`. En esas tres, saber cuándo fue la última modificación es información de diagnóstico real.

#### Mantenimiento de `updated_at`

`DEFAULT NOW()` **solo cubre la inserción**. Una columna `updated_at` con únicamente un default queda congelada en el instante del `INSERT` y miente a partir del primer `UPDATE`. El valor se mantiene con un trigger `BEFORE UPDATE` en PostgreSQL.

La función es una sola, reutilizable por todas las tablas:

```sql
-- =========================================================
-- Auditoría temporal: función compartida de updated_at
-- =========================================================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

Y un trigger por cada tabla que tenga la columna:

```sql
-- =========================================================
-- Auditoría temporal: triggers por tabla
-- =========================================================
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_course_offerings_updated_at
    BEFORE UPDATE ON course_offerings
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_enrollments_updated_at
    BEFORE UPDATE ON enrollments
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

#### Por qué un trigger y no `onupdate=func.now()`

SQLAlchemy ofrece `onupdate=func.now()` a nivel de columna, pero solo actúa sobre las escrituras que pasan por el ORM. El trigger cubre **toda** escritura sobre la tabla: las del ORM, las de una migración de Alembic, las de un script de mantenimiento y las de una sesión manual de `psql`. La diferencia importa porque `updated_at` es una garantía del dato, no una convención de la aplicación: si una corrección hecha por `psql` deja la columna sin tocar, la columna deja de ser confiable para auditoría y para depurar incidentes.

#### Nota operativa

La función `set_updated_at()` se crea **una sola vez**, en la migración que introduce la primera tabla con `updated_at`. Las migraciones posteriores que añadan una tabla con esa columna solo agregan su `CREATE TRIGGER`; no vuelven a definir la función. El `CREATE OR REPLACE` la hace idempotente por si una migración necesita redefinirla.

### Ausencias intencionales

Algunas decisiones que se dejaron fuera y por qué:

- **No hay tabla de "carrito" de matrícula.** El estudiante inscribe materia por materia; agregar carrito es una mejora futura, no un requisito del núcleo.
- **No se modelan pagos.** El sistema es de gestión académica, no financiera. La integración con cartera es un módulo aparte.
- **No hay lista de espera automática.** El estado `WAITLISTED` existe en el enum como preparación, pero la lógica de promoción automática se posterga a una siguiente iteración.

Estas ausencias siguen el principio YAGNI: no se implementa lo que no se necesita todavía.

## 4. Datos de referencia

Al arrancar el sistema por primera vez se cargan datos mínimos mediante un seed script:

- 3 programas académicos de ejemplo
- 10 profesores
- 16 materias con sus requisitos
- 9 espacios físicos (aulas, laboratorios y un auditorio)
- 1 período de matrícula activo
- 21 grupos de oferta con horarios y cupos
- 50 estudiantes de prueba

El seed es idempotente: puede ejecutarse múltiples veces sin duplicar datos.

**Cómo se consigue la idempotencia.** Cada fila se busca por su **clave natural** —el `code` de un programa o una materia, el `student_code` de un estudiante, el correo de una cuenta— y solo se inserta si falta. Nunca por el identificador, porque los UUID los genera PostgreSQL y serían distintos en cada ejecución. Eso permite ejecutarlo como paso rutinario tras levantar el entorno sin tener que recordar si ya estaba sembrado.

Lo que ya existe **no se sobrescribe**: si durante una prueba se cambió el cupo de un grupo a mano, volver a sembrar no lo revierte. Para partir de cero está `make clean`, que borra los volúmenes.

Detalles de la implementación (`backend/app/infrastructure/seed.py`):

- El período de matrícula se crea **abierto alrededor del instante actual**, no con fechas fijas: un período que naciera cerrado obligaría a tocar la base a mano antes de poder probar nada.
- Las materias de Ingeniería forman una cadena de prerrequisitos de tres niveles (`MAT101` → `MAT102` → `MAT201`), pensada para ejercitar la validación de la Fase 3 en más de un salto.
- Los correquisitos cubren los dos casos que se validan distinto: `FIS101` exige cursar `MAT101` a la vez (simple, en un solo sentido), y `FIS101` y `FIS102` se exigen mutuamente (el bloque teoría + laboratorio). Sus grupos van en franjas que no chocan entre sí: sin eso el bloque sería inscribible en teoría e imposible en la práctica.
- Los grupos reciben ocupaciones variadas pero **deterministas**, de forma que el catálogo muestre grupos con holgura, casi llenos y llenos del todo sin depender del azar.
- Todas las cuentas comparten la contraseña `SecurePass123`. Es un dato de desarrollo: el seed no se ejecuta en DEV, STAGING ni PROD, donde las cuentas reales se crean por los endpoints de administración.
