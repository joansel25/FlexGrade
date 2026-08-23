"""Constructores de entidades de prueba.

Centralizan los valores por defecto para que el bloque *arrange* de cada test
mencione solo lo que ese test necesita, y no una lista de campos irrelevantes.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4

from app.domain.entities.course import Course
from app.domain.entities.course_offering import CourseOffering
from app.domain.entities.enrollment_period import EnrollmentPeriod
from app.domain.entities.professor import Professor
from app.domain.entities.program import Program
from app.domain.entities.student import Student
from app.domain.entities.user import User
from app.domain.value_objects.course_code import CourseCode
from app.domain.value_objects.email import Email
from app.domain.value_objects.schedule_block import ScheduleBlock
from app.domain.value_objects.student_code import StudentCode
from app.domain.value_objects.user_role import UserRole

PASSWORD_POR_DEFECTO = "SecurePass123"

# Instante de referencia de los tests del catálogo. Fijo y explícito: una prueba que dependa
# de `datetime.now()` pasa hoy y falla el día que la ventana de matrícula quede en el pasado.
AHORA = datetime(2025, 11, 16, 12, 0, tzinfo=UTC)


def crear_usuario(
    *,
    user_id: UUID | None = None,
    email: str = "estudiante@tdea.edu.co",
    password: str = PASSWORD_POR_DEFECTO,
    role: UserRole = UserRole.STUDENT,
    is_active: bool = True,
) -> User:
    """Construye un `User` cuyo hash coincide con el de `FakeAuthService`."""
    return User(
        id=user_id or uuid4(),
        email=Email(email),
        password_hash=f"hashed::{password}",
        role=role,
        is_active=is_active,
    )


def crear_estudiante(
    *,
    student_id: UUID | None = None,
    user_id: UUID | None = None,
    student_code: str = "1234567",
    program_id: UUID | None = None,
    current_semester: int = 6,
    full_name: str = "Joan Sebastián Cárdenas",
) -> Student:
    """Construye un `Student` con datos académicos verosímiles."""
    return Student(
        id=student_id or uuid4(),
        user_id=user_id or uuid4(),
        student_code=StudentCode(student_code),
        program_id=program_id or uuid4(),
        current_semester=current_semester,
        full_name=full_name,
        enrollment_date=date(2022, 1, 15),
    )


def crear_programa(
    *,
    program_id: UUID | None = None,
    code: str = "ISIS",
    name: str = "Ingeniería de Sistemas",
    total_semesters: int = 10,
) -> Program:
    """Construye un `Program`."""
    return Program(
        id=program_id or uuid4(),
        code=code,
        name=name,
        total_semesters=total_semesters,
    )


def crear_materia(
    *,
    course_id: UUID | None = None,
    code: str = "MAT101",
    name: str = "Cálculo I",
    credits: int = 4,
    description: str | None = "Fundamentos de cálculo diferencial",
) -> Course:
    """Construye un `Course` del catálogo."""
    return Course(
        id=course_id or uuid4(),
        code=CourseCode(code),
        name=name,
        credits=credits,
        description=description,
    )


def crear_profesor(
    *,
    professor_id: UUID | None = None,
    full_name: str = "Ana Pérez",
    email: str | None = "ana.perez@tdea.edu.co",
) -> Professor:
    """Construye un `Professor`."""
    return Professor(id=professor_id or uuid4(), full_name=full_name, email=email)


def crear_periodo(
    *,
    period_id: UUID | None = None,
    code: str = "2025-2-V1",
    academic_period: str = "2025-2",
    name: str = "Matrícula 2025-2 primera vuelta",
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    is_active: bool = True,
) -> EnrollmentPeriod:
    """Construye un `EnrollmentPeriod` abierto alrededor de `AHORA` por defecto."""
    return EnrollmentPeriod(
        id=period_id or uuid4(),
        code=code,
        academic_period=academic_period,
        name=name,
        starts_at=starts_at if starts_at is not None else AHORA - timedelta(days=1),
        ends_at=ends_at if ends_at is not None else AHORA + timedelta(days=1),
        is_active=is_active,
    )


def crear_franja(
    *,
    day_of_week: int = 1,
    start_time: time = time(8, 0),
    end_time: time = time(10, 0),
    classroom: str | None = "A-201",
) -> ScheduleBlock:
    """Construye un `ScheduleBlock`."""
    return ScheduleBlock(
        day_of_week=day_of_week,
        start_time=start_time,
        end_time=end_time,
        classroom=classroom,
    )


def crear_oferta(
    *,
    offering_id: UUID | None = None,
    enrollment_period_id: UUID | None = None,
    course_id: UUID | None = None,
    group_number: str = "01",
    total_capacity: int = 40,
    enrolled_count: int = 0,
    version: int = 0,
    professor: Professor | None = None,
    schedule: tuple[ScheduleBlock, ...] = (),
) -> CourseOffering:
    """Construye un `CourseOffering` con su docente y su horario."""
    return CourseOffering(
        id=offering_id or uuid4(),
        enrollment_period_id=enrollment_period_id or uuid4(),
        course_id=course_id or uuid4(),
        group_number=group_number,
        total_capacity=total_capacity,
        enrolled_count=enrolled_count,
        version=version,
        professor=professor,
        schedule=schedule,
    )
