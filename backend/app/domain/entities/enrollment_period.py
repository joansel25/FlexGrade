"""Entidad EnrollmentPeriod: la ventana temporal de matrícula."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass
class EnrollmentPeriod:
    """Ventana durante la cual se permite matricularse.

    Es la entidad que decide *cuándo* se puede inscribir. Todo el requisito no funcional del
    sistema —5.000 estudiantes concurrentes— ocurre dentro de las pocas horas que dura una de
    estas ventanas.

    Attributes:
        id: identificador único del período.
        code: código único de la ventana (por ejemplo `2025-2-V1`).
        academic_period: semestre académico al que pertenece (por ejemplo `2025-2`). Varias
            ventanas del mismo semestre —primera vuelta, ajustes— comparten este valor.
        name: nombre legible para mostrar al estudiante.
        starts_at: instante de apertura.
        ends_at: instante de cierre.
        is_active: si un administrador la ha activado.
        created_at: instante de creación del registro.
    """

    id: UUID
    code: str
    academic_period: str
    name: str
    starts_at: datetime
    ends_at: datetime
    is_active: bool
    created_at: datetime | None = field(default=None)

    def is_open(self, now: datetime) -> bool:
        """Indica si en este instante se puede matricular.

        Exige las dos condiciones a la vez: que un administrador haya activado la ventana y
        que el instante caiga dentro del rango de fechas. Están separadas a propósito: la
        activación permite dejar un período preparado con semanas de antelación sin que se
        abra solo al llegar la fecha, y permite cerrarlo de inmediato ante un incidente sin
        tener que tocar las fechas.

        Args:
            now: el instante a evaluar. Se recibe como parámetro en vez de leer el reloj
                aquí dentro para que la regla sea comprobable sin depender de la hora real.

        Returns:
            `True` si la ventana admite inscripciones ahora mismo.
        """
        return self.is_active and self.starts_at <= now <= self.ends_at

    def time_remaining_seconds(self, now: datetime) -> int:
        """Segundos que quedan hasta el cierre de la ventana.

        Alimenta la cuenta atrás que ve el estudiante durante la matrícula.

        Args:
            now: el instante desde el que se cuenta.

        Returns:
            Los segundos restantes, o `0` si la ventana ya cerró. Nunca un número negativo:
            "quedan -3.600 segundos" no significa nada para quien lo lee.
        """
        restantes = (self.ends_at - now).total_seconds()
        return max(0, int(restantes))
