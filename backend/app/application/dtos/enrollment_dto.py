"""DTOs del flujo de inscripción y del horario del estudiante."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from uuid import UUID

from app.domain.value_objects.enrollment_status import EnrollmentStatus


@dataclass(frozen=True)
class EnrollmentDTO:
    """Resultado de `POST /enrollments`.

    Lleva el código y el nombre de la materia además de los identificadores porque `API.md` los
    incluye en la respuesta: el estudiante acaba de inscribirse y necesita leer «MAT101 —
    Cálculo I, grupo 01», no tres UUID. Resolverlos en el router obligaría a una consulta más
    después de cerrar la transacción.

    Attributes:
        id: identificador de la inscripción.
        student_id: estudiante inscrito.
        course_offering_id: grupo en el que quedó inscrito.
        course_code: código de la materia (por ejemplo `MAT101`).
        course_name: nombre de la materia.
        group_number: número del grupo.
        enrolled_at: instante de la inscripción, según la base de datos.
        status: estado resultante.
    """

    id: UUID
    student_id: UUID
    course_offering_id: UUID
    course_code: str
    course_name: str
    group_number: str
    enrolled_at: datetime | None
    status: EnrollmentStatus


@dataclass(frozen=True)
class ScheduleBlockDTO:
    """Una franja del horario del estudiante, con el contexto que la hace legible.

    Lleva el código y el nombre de la materia además del día y la hora porque un horario que
    solo dijera «lunes 8:00–10:00» no le sirve a nadie: hay que saber a qué clase ir.

    Attributes:
        course_code: código de la materia (por ejemplo `MAT101`).
        course_name: nombre de la materia.
        group_number: número del grupo.
        professor: nombre del docente, o `None` si aún no se ha asignado.
        day_of_week: día de la semana, de 1 (lunes) a 7 (domingo).
        start_time: hora de inicio.
        end_time: hora de fin.
        classroom: aula, si ya se asignó.
    """

    course_code: str
    course_name: str
    group_number: str
    professor: str | None
    day_of_week: int
    start_time: time
    end_time: time
    classroom: str | None


@dataclass(frozen=True)
class StudentScheduleDTO:
    """Resultado de `GET /students/me/schedule`.

    Attributes:
        academic_period: semestre al que corresponde el horario (por ejemplo `2025-2`).
        blocks: las franjas, ordenadas por día y hora. Vacía si no tiene nada inscrito, que es
            un resultado legítimo y no un error.
    """

    academic_period: str
    blocks: list[ScheduleBlockDTO] = field(default_factory=list)


@dataclass(frozen=True)
class StudentEnrollmentDTO:
    """Una inscripción activa del estudiante, con el contexto que la hace accionable.

    Lleva el identificador de la INSCRIPCIÓN, no solo el del grupo, y esa es su razón de ser:
    es lo que permite cancelarla con `DELETE /enrollments/{id}`. El horario
    (`StudentScheduleDTO`) no sirve para eso —está pensado para leerse, no para operar sobre
    él— y sus franjas no tienen identidad propia.

    Attributes:
        id: identificador de la inscripción.
        course_offering_id: grupo inscrito.
        course_id: materia, para poder enlazar con su ficha del catálogo.
        course_code: código de la materia (por ejemplo `MAT101`).
        course_name: nombre de la materia.
        credits: créditos que otorga. Permite mostrar la carga total del semestre sin una
            consulta más por materia.
        group_number: número del grupo.
        professor: nombre del docente, o `None` si aún no se ha asignado.
        schedule: franjas del grupo, ordenadas por día y hora.
        enrolled_at: instante de la inscripción, según la base de datos.
        pending_corequisites: códigos de las materias que esta exige cursar a la vez y que el
            estudiante todavía NO tiene inscritas ni aprobadas. Casi siempre va vacío. Cuando
            no lo está, la matrícula está incompleta: es el estado intermedio que deja el
            bloque de correquisitos mutuos, donde se permite entrar de una en una y por tanto
            existe un momento en que solo hay media pareja inscrita. Se calcula en el servidor
            porque es la misma regla que decide si la inscripción se acepta.
    """

    id: UUID
    course_offering_id: UUID
    course_id: UUID
    course_code: str
    course_name: str
    credits: int
    group_number: str
    professor: str | None
    schedule: list[ScheduleBlockDTO]
    enrolled_at: datetime | None
    pending_corequisites: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StudentEnrollmentsDTO:
    """Resultado de `GET /students/me/enrollments`.

    Attributes:
        academic_period: semestre al que corresponden (por ejemplo `2025-2`).
        period_code: código de la ventana de matrícula.
        items: las inscripciones activas, ordenadas por código de materia.
        total_credits: suma de los créditos inscritos. Se calcula aquí y no en el frontend
            para que la cifra sea la misma en el comprobante en PDF y en la pantalla.
    """

    academic_period: str
    period_code: str
    items: list[StudentEnrollmentDTO] = field(default_factory=list)
    total_credits: int = 0


@dataclass(frozen=True)
class CancelledEnrollmentDTO:
    """Una inscripción que quedó cancelada, descrita para poder nombrarla.

    Attributes:
        id: identificador de la inscripción cancelada.
        course_offering_id: grupo cuyo cupo se liberó.
        course_code: código de la materia (por ejemplo `MAT101`).
        course_name: nombre de la materia.
        group_number: número del grupo.
    """

    id: UUID
    course_offering_id: UUID
    course_code: str
    course_name: str
    group_number: str


@dataclass(frozen=True)
class CancellationDTO:
    """Resultado de `DELETE /enrollments/{id}`.

    Es una LISTA y no una sola inscripción porque cancelar puede arrastrar más de una: las
    materias unidas por correquisitos mutuos se abandonan como un bloque, igual que se cursan
    como un bloque. La operación devolvía `204 No Content` hasta esta iteración; con el arrastre
    eso dejaría que dos materias desaparecieran de la pantalla tras pulsar «Cancelar» en una
    sola, sin nada que lo explicara.

    Attributes:
        items: lo que quedó cancelado, empezando por la inscripción que se pidió cancelar.
    """

    items: list[CancelledEnrollmentDTO] = field(default_factory=list)

    def arrastro_otras(self) -> bool:
        """Indica si la cancelación afectó a algo más que la inscripción pedida."""
        return len(self.items) > 1
