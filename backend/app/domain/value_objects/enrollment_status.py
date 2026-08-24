"""Estado de una inscripción."""

from __future__ import annotations

from enum import Enum


class EnrollmentStatus(str, Enum):
    """Estados reconocidos, alineados con el CHECK de `enrollments.status`.

    Hereda de `str` para que se serialice y compare como texto sin conversiones manuales en
    las capas externas, manteniendo a la vez el conjunto cerrado.

    `WAITLISTED` existe porque el esquema lo admite, pero **ninguna operación lo produce**: la
    lista de espera es una ausencia intencional del alcance (`DATA_MODEL.md`). Está aquí para
    que una fila con ese estado, si algún día la crea otro camino, se lea sin fallar.
    """

    ENROLLED = "ENROLLED"
    CANCELLED = "CANCELLED"
    WAITLISTED = "WAITLISTED"

    def __str__(self) -> str:
        return self.value
