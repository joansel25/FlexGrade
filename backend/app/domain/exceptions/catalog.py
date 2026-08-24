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


class PeriodNotFoundError(DomainError):
    """La ventana de matrícula solicitada no existe.

    Vive aquí y no en `admin.py`, junto a `CourseNotFoundError` y `OfferingNotFoundError`: es
    el mismo tipo de fallo —un identificador que no corresponde a nada— y agruparlos hace que
    se lean juntos. `admin.py` guarda las reglas propias de la administración, no sus búsquedas
    fallidas.
    """

    def __init__(self, period_id: UUID) -> None:
        super().__init__(
            "El período de matrícula solicitado no existe",
            details={"period_id": str(period_id)},
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


class ProfessorNotFoundError(DomainError):
    """El docente indicado no existe.

    Vive aquí por la misma razón que `PeriodNotFoundError`: es una búsqueda que no encuentra
    nada, no una regla de administración. La comprobación existe porque la clave foránea de
    `course_offerings.professor_id` fallaría con un error de integridad opaco —y un 500— en
    lugar de decir que el identificador no corresponde a ningún docente.
    """

    def __init__(self, professor_id: UUID) -> None:
        super().__init__(
            "El docente indicado no existe",
            details={"professor_id": str(professor_id)},
        )
