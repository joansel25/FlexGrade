"""Errores del dominio de administración académica.

Existen para que las operaciones de administración fallen con un mensaje que diga qué pasó, en
vez de con el error de restricción que devolvería PostgreSQL. Las restricciones de la base
siguen ahí y son la garantía final; estas excepciones son la primera línea, la que produce una
respuesta que alguien puede leer y corregir.
"""

from __future__ import annotations

from datetime import datetime

from app.domain.exceptions.base import DomainError


class InvalidPeriodRangeError(DomainError):
    """La ventana termina antes de empezar, o en el mismo instante."""

    def __init__(self, starts_at: datetime, ends_at: datetime) -> None:
        super().__init__(
            "La fecha de cierre debe ser posterior a la de apertura",
            details={"starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat()},
        )


class DuplicatePeriodCodeError(DomainError):
    """Ya existe una ventana de matrícula con ese código."""

    def __init__(self, code: str) -> None:
        super().__init__(
            "Ya existe un período de matrícula con ese código",
            details={"code": code},
        )
