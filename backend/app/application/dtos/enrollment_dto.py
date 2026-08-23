"""DTOs del flujo de inscripción."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
