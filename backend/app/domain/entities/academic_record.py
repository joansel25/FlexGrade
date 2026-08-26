"""Entidad `AcademicRecord`: una materia terminada en el expediente de alguien."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.domain.value_objects.grade import Grade
from app.domain.value_objects.history_status import HistoryStatus


@dataclass
class AcademicRecord:
    """Una fila del historial académico: qué cursó alguien, cuándo y con qué resultado.

    ES EL REGISTRO DEFINITIVO, y por eso la Fase 9 lo separa de la nota que pone el docente.
    Aquella vive en la inscripción y se corrige tantas veces como haga falta; esta se escribe una
    sola vez, en la consolidación del período, y a partir de ahí decide prerrequisitos y aparece
    en el expediente.

    El `status` se DERIVA de la nota y no se recibe: dejar que quien construye el registro
    decida si aprueba abriría la puerta a un expediente donde un 4.5 figura como perdido. La
    regla —aprueba desde 3.0— vive en `Grade` y en un solo sitio.

    Attributes:
        id: identificador único.
        student_id: de quién es el expediente.
        course_id: la materia cursada. No el grupo: al expediente le da igual con quién se vio.
        academic_period: el semestre, por ejemplo `2025-2`. NO la ventana de matrícula: dos
            vueltas de la misma matrícula son el mismo semestre para el expediente.
        final_grade: la nota con la que terminó.
        status: aprobada o perdida, derivado de la nota.
        created_at: instante en que se consolidó.
    """

    id: UUID
    student_id: UUID
    course_id: UUID
    academic_period: str
    final_grade: Grade
    status: HistoryStatus
    created_at: datetime | None = field(default=None)

    @classmethod
    def consolidate(
        cls, *, student_id: UUID, course_id: UUID, academic_period: str, final_grade: Grade
    ) -> AcademicRecord:
        """Crea el registro derivando el resultado de la nota.

        Es el único constructor que se usa: `status` no se pasa desde fuera para que no pueda
        contradecir a la nota.
        """
        return cls(
            id=uuid4(),
            student_id=student_id,
            course_id=course_id,
            academic_period=academic_period,
            final_grade=final_grade,
            status=HistoryStatus.APPROVED if final_grade.aprueba() else HistoryStatus.FAILED,
        )
