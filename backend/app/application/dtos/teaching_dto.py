"""DTOs de la carga docente (Fase 9)."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.entities.course import Course
from app.domain.entities.course_offering import CourseOffering
from app.domain.entities.enrollment import Enrollment
from app.domain.entities.student import Student


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


@dataclass(frozen=True)
class GradeEntryDTO:
    """Una fila de la lista del grupo: quién es y qué nota lleva.

    Lleva la INSCRIPCIÓN entera y no solo la nota porque el docente necesita distinguir «aún no
    la he puesto» de «le puse 0.0», que son cosas opuestas y con el número suelto se ven igual.

    Attributes:
        student: el perfil, con su código y su nombre.
        enrollment: la inscripción, con la nota si la tiene y cuándo se puso.
    """

    student: Student
    enrollment: Enrollment


@dataclass(frozen=True)
class OfferingRosterDTO:
    """La lista completa de un grupo.

    Attributes:
        offering: el grupo.
        course: la materia que se dicta.
        entries: los inscritos, ordenados por nombre. Solo los vivos: quien canceló no cursó.
        pending: cuántos quedan sin calificar. Es la cifra que le dice al docente si terminó, y
            se cuenta aquí para que la interfaz no tenga que recorrer la lista para saberlo.
    """

    offering: CourseOffering
    course: Course
    entries: list[GradeEntryDTO] = field(default_factory=list)
    pending: int = 0
