# Modelo de datos

Este documento describe el modelo de datos del Sistema de Matrícula Académica: las entidades del dominio, sus relaciones y el esquema SQL de PostgreSQL. Cada entidad tiene un propósito claro derivado de un caso de uso real; no hay tablas ni columnas de relleno.

## 1. Entidades del dominio

### Contexto

El dominio de matrícula académica gira alrededor de tres ideas centrales:

1. Un **estudiante** pertenece a un **programa** académico.
2. Un **programa** tiene un plan de estudios compuesto por **materias** con prerrequisitos entre sí.
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
| **Prerequisite** | Relación de prerrequisitos entre materias | Un Course puede requerir haber aprobado otros Courses |
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

CREATE INDEX idx_users_email ON users(email);

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

CREATE INDEX idx_students_program ON students(program_id);
CREATE INDEX idx_students_code ON students(student_code);

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

CREATE INDEX idx_courses_code ON courses(code);

CREATE TABLE program_courses (
    program_id UUID NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    suggested_semester INTEGER NOT NULL CHECK (suggested_semester >= 1),
    is_mandatory BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (program_id, course_id)
);

CREATE TABLE course_prerequisites (
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    required_course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    PRIMARY KEY (course_id, required_course_id),
    CHECK (course_id <> required_course_id)
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

CREATE INDEX idx_enrollment_periods_active ON enrollment_periods(is_active) WHERE is_active = TRUE;

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
    UNIQUE (enrollment_period_id, course_id, group_number),
    CHECK (enrolled_count <= total_capacity)
);

CREATE INDEX idx_offerings_period ON course_offerings(enrollment_period_id);
CREATE INDEX idx_offerings_course ON course_offerings(course_id);

CREATE TABLE schedule_blocks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_offering_id UUID NOT NULL REFERENCES course_offerings(id) ON DELETE CASCADE,
    day_of_week SMALLINT NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),  -- 1=Lun, 7=Dom
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    classroom VARCHAR(50),
    CHECK (end_time > start_time)
);

CREATE INDEX idx_schedule_offering ON schedule_blocks(course_offering_id);

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
    UNIQUE (student_id, course_offering_id, enrollment_period_id)
);

CREATE INDEX idx_enrollments_student ON enrollments(student_id);
CREATE INDEX idx_enrollments_offering ON enrollments(course_offering_id);
CREATE INDEX idx_enrollments_period ON enrollments(enrollment_period_id);
CREATE INDEX idx_enrollments_active ON enrollments(status) WHERE status = 'ENROLLED';

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

CREATE INDEX idx_history_student ON academic_history(student_id);
CREATE INDEX idx_history_student_status ON academic_history(student_id, status);
```

## 3. Notas de diseño

### Concurrencia en el descuento de cupos

El campo `course_offerings.enrolled_count` se actualiza durante la inscripción en un contexto de alta concurrencia. Para evitar sobrecupo se combinan dos mecanismos:

1. **Bloqueo optimista** mediante el campo `version`. Cada actualización incrementa `version` y el UPDATE usa `WHERE version = ?` para detectar conflictos.
2. **Restricción CHECK** a nivel de base de datos (`enrolled_count <= total_capacity`) como red de seguridad final. Si por alguna razón el bloqueo optimista falla, PostgreSQL rechaza la operación.

En la capa de aplicación, la inscripción se ejecuta dentro de una transacción explícita con reintentos limitados ante conflictos de versión.

### Caché de consultas frecuentes

Las consultas de catálogo (listado de materias, disponibilidad de grupos) son las de mayor frecuencia durante el pico. Se cachean en Redis con TTL corto (30-60 segundos), lo suficiente para absorber miles de consultas idénticas sin golpear la base de datos.

**No se cachea** la operación de inscripción ni la disponibilidad exacta en el momento del descuento: siempre consultan directo a PostgreSQL para garantizar consistencia.

### Prerrequisitos

Se modelan como una relación autoreferente sobre `courses`. Al inscribir un estudiante, la validación consulta `academic_history` filtrando por `status = 'APPROVED'` para verificar que todos los prerrequisitos estén cumplidos.

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
- 15 materias con sus prerrequisitos
- 1 período de matrícula activo
- 20 grupos de oferta con horarios y cupos
- 50 estudiantes de prueba

El seed es idempotente: puede ejecutarse múltiples veces sin duplicar datos.
