"""DTOs de la carga docente (Fase 9)."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.entities.course import Course
from app.domain.entities.course_offering import CourseOffering


@dataclass(frozen=True)
class ProfessorOfferingDTO:
    """Un grupo que dicta el docente, con su materia ya resuelta.

    Compone dos agregados —el grupo y la materia— que el docente ve como una sola cosa. Sin
    esto, la interfaz recibiría un `course_id` y tendría que cruzarlo contra otra lista para
    escribir el nombre.

    Attributes:
        offering: el grupo, con su cupo, su horario y su docente.
        course: la materia que se dicta.
    """

    offering: CourseOffering
    course: Course


@dataclass(frozen=True)
class ProfessorOfferingsDTO:
    """La carga docente de un período.

    `period_code` y `academic_period` van en `None` cuando no hay ventana activa. Es un estado
    normal —entre semestres no hay ninguna— y la lista vacía sin período dice exactamente eso,
    mientras que una lista vacía con período diría algo distinto: que hay semestre y este
    docente no tiene carga.

    Attributes:
        period_code: código de la ventana activa, o `None` si no hay ninguna.
        academic_period: semestre al que pertenece, o `None`.
        offerings: los grupos, ordenados por número de grupo.
    """

    period_code: str | None
    academic_period: str | None
    offerings: list[ProfessorOfferingDTO] = field(default_factory=list)
