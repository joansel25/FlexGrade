"""Requisito académico: una materia exigida por otra dentro de un plan de estudios."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.entities.course import Course
from app.domain.value_objects.requirement_type import RequirementType


@dataclass(frozen=True)
class CourseRequirement:
    """Una materia exigida, junto con la forma en que se exige.

    Es lo que devuelve el repositorio cuando se le piden los requisitos de una materia dentro
    de un programa. Va en el dominio y no en un DTO de aplicación porque los validadores lo
    reciben y deciden sobre él: es parte del vocabulario de la regla, no del transporte.

    El **programa no viaja dentro**. Quien consulta los requisitos ya eligió el plan sobre el
    que pregunta —el del estudiante que se inscribe, o el que llega en la petición—, así que
    repetirlo en cada elemento de la lista sería un dato redundante que puede contradecir al
    de la consulta.

    Attributes:
        course: la materia exigida.
        requirement_type: si hay que haberla aprobado antes (`PREREQUISITE`) o cursarla al
            mismo tiempo (`COREQUISITE`).
    """

    course: Course
    requirement_type: RequirementType

    def is_prerequisite(self) -> bool:
        """Indica si el requisito se cumple con el historial académico."""
        return self.requirement_type is RequirementType.PREREQUISITE

    def is_corequisite(self) -> bool:
        """Indica si el requisito se cumple con las inscripciones del período vigente."""
        return self.requirement_type is RequirementType.COREQUISITE
