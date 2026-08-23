"""Errores del dominio del catálogo académico."""

from __future__ import annotations

from uuid import UUID

from app.domain.exceptions.base import DomainError


class CourseNotFoundError(DomainError):
    """La materia solicitada no existe en el catálogo."""

    def __init__(self, course_id: UUID) -> None:
        super().__init__(
            "La materia solicitada no existe",
            details={"course_id": str(course_id)},
        )


class OfferingNotFoundError(DomainError):
    """El grupo solicitado no existe."""

    def __init__(self, offering_id: UUID) -> None:
        super().__init__(
            "El grupo solicitado no existe",
            details={"offering_id": str(offering_id)},
        )


class NoActivePeriodError(DomainError):
    """No hay ninguna ventana de matrícula abierta en este momento.

    No es un error del servidor ni una petición mal formada: es el estado normal del sistema
    durante la mayor parte del semestre. Se modela como excepción de dominio para que la API
    responda 404 con un mensaje claro en vez de una lista vacía que el frontend tendría que
    interpretar.
    """

    def __init__(self) -> None:
        super().__init__("No hay un período de matrícula activo")
