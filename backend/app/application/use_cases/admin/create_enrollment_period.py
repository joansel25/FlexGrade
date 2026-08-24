"""Caso de uso: crear una ventana de matrícula."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.application.ports.repositories.period_repository import PeriodRepository
from app.application.ports.unit_of_work import UnitOfWork
from app.domain.entities.enrollment_period import EnrollmentPeriod
from app.domain.exceptions.admin import DuplicatePeriodCodeError, InvalidPeriodRangeError


class CreateEnrollmentPeriodUseCase:
    """Registra una ventana de matrícula nueva, siempre desactivada.

    Crear y activar son operaciones separadas a propósito. Una ventana nace cerrada y se abre
    después, con `PUT /admin/enrollment-periods/{id}/activate`: eso permite prepararla con
    semanas de antelación —revisando fechas, creando sus grupos— sin que se abra sola al
    llegar la fecha, y permite cerrarla de inmediato ante un incidente sin tener que tocar el
    calendario.
    """

    def __init__(self, period_repository: PeriodRepository, unit_of_work: UnitOfWork) -> None:
        self._periods = period_repository
        self._uow = unit_of_work

    def execute(
        self,
        *,
        code: str,
        academic_period: str,
        name: str,
        starts_at: datetime,
        ends_at: datetime,
    ) -> EnrollmentPeriod:
        """Crea la ventana.

        Args:
            code: código único (por ejemplo `2026-1-V1`).
            academic_period: semestre al que pertenece (por ejemplo `2026-1`). Varias ventanas
                del mismo semestre —primera vuelta, ajustes— comparten este valor.
            name: nombre legible para el estudiante.
            starts_at: instante de apertura.
            ends_at: instante de cierre.

        Returns:
            La ventana creada, desactivada.

        Raises:
            InvalidPeriodRangeError: si el cierre no es posterior a la apertura.
            DuplicatePeriodCodeError: si ya existe una ventana con ese código.
        """
        # El `CHECK (ends_at > starts_at)` de PostgreSQL también lo impediría, pero devolvería
        # un error de restricción opaco. Comprobarlo aquí permite decir qué fechas se
        # recibieron, que es lo que necesita quien está creando el período.
        if ends_at <= starts_at:
            raise InvalidPeriodRangeError(starts_at, ends_at)

        with self._uow:
            # Igual con la restricción UNIQUE: sin esta consulta, un código repetido llegaría
            # como «duplicate key value violates unique constraint», que no dice nada útil.
            if self._periods.find_by_code(code) is not None:
                raise DuplicatePeriodCodeError(code)

            periodo = EnrollmentPeriod(
                id=uuid4(),
                code=code,
                academic_period=academic_period,
                name=name,
                starts_at=starts_at,
                ends_at=ends_at,
                is_active=False,
            )

            self._periods.save(periodo)
            self._uow.commit()

        return periodo
