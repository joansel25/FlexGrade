"""DTOs del catálogo académico.

Existen solo donde el resultado **compone varios agregados** y por tanto no cabe en ninguna
entidad: el detalle de una materia junto a sus prerrequisitos, los grupos junto a la materia y
el período en que se dictan, o un período junto a su cuenta atrás.

Cuando el resultado es una única entidad —el listado de materias, el detalle de un grupo— el
caso de uso la devuelve tal cual y el router la traduce a su schema. Envolverla en un DTO que
copiase los mismos campos sería una capa de indirección que no aporta nada.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.entities.course import Course
from app.domain.entities.course_offering import CourseOffering
from app.domain.entities.enrollment_period import EnrollmentPeriod


@dataclass(frozen=True)
class CourseDetailDTO:
    """Resultado de `GET /courses/{id}`: la materia y sus prerrequisitos directos.

    Attributes:
        course: la materia consultada.
        prerequisites: las materias que hay que haber aprobado antes. Vacía si no tiene.
    """

    course: Course
    prerequisites: list[Course] = field(default_factory=list)


@dataclass(frozen=True)
class CourseOfferingsDTO:
    """Resultado de `GET /courses/{id}/offerings`: los grupos de una materia.

    Lleva la materia y el período además de los grupos porque la respuesta los incluye
    (`course_code`, `period_code`) y resolverlos en el router obligaría a consultarlos otra
    vez.

    Attributes:
        course: la materia consultada.
        period: el período de matrícula activo en el que se ofrecen los grupos.
        offerings: los grupos, ordenados por número de grupo. Vacía si la materia no se
            ofrece en este período.
    """

    course: Course
    period: EnrollmentPeriod
    offerings: list[CourseOffering] = field(default_factory=list)


@dataclass(frozen=True)
class CurrentPeriodDTO:
    """Resultado de `GET /enrollment-periods/current`: el período y su estado en vivo.

    Attributes:
        period: el período activo.
        is_open: si admite inscripciones en este instante. No coincide con `period.is_active`:
            un período puede estar activado y todavía no haber empezado, o ya haber cerrado.
        time_remaining_seconds: segundos hasta el cierre; `0` si ya cerró.
    """

    period: EnrollmentPeriod
    is_open: bool
    time_remaining_seconds: int
