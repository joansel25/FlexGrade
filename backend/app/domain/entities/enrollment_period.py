"""Entidad EnrollmentPeriod: la ventana temporal de matrícula."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.domain.exceptions.admin import PeriodAlreadyConsolidatedError


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
        consolidated_at: instante en que el semestre se cerró y sus notas pasaron al historial,
            o `None` mientras no haya ocurrido. Es una FECHA y no un booleano: lo primero que se
            pregunta cuando alguien reclama una nota es si el cierre fue antes o después de que
            la corrigieran, y eso no se reconstruye a posteriori.
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
    consolidated_at: datetime | None = field(default=None)

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

    def esta_consolidado(self) -> bool:
        """Indica si el semestre ya se cerró y sus notas viajaron al historial.

        Un período consolidado no admite nada más: ni matrículas, ni cambios de nota, ni una
        segunda consolidación. Es el único estado irreversible del sistema, y por eso todo lo
        que lo produce se comprueba antes en vez de después.
        """
        return self.consolidated_at is not None

    def consolidate(self, *, now: datetime) -> None:
        """Marca el semestre como cerrado.

        Desactiva la ventana en el mismo gesto, y no como un paso aparte que alguien pueda
        olvidar: un período consolidado y activo permitiría matricularse en un semestre cuyo
        expediente ya se escribió, y esas inscripciones no llegarían nunca al historial porque
        la consolidación ya pasó. La base lo respalda con un `CHECK`.

        Raises:
            PeriodAlreadyConsolidatedError: si ya se había consolidado. Repetirlo duplicaría
                las filas del expediente, y el `UNIQUE` de `academic_history` lo rechazaría con
                un error de restricción que no dice qué pasó.
        """
        if self.esta_consolidado():
            raise PeriodAlreadyConsolidatedError(self.id, self.consolidated_at)

        self.consolidated_at = now
        self.is_active = False

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
