"""Caso de uso: consultar la ventana de matrícula vigente."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from app.application.dtos.catalog_dto import CurrentPeriodDTO
from app.application.ports.repositories.period_repository import PeriodRepository
from app.domain.exceptions.catalog import NoActivePeriodError

Clock = Callable[[], datetime]


def _reloj_del_sistema() -> datetime:
    """Instante actual en UTC. Toda fecha del sistema viaja en UTC (`API.md`)."""
    return datetime.now(UTC)


class GetCurrentPeriodUseCase:
    """Devuelve el período activo junto con su estado en vivo."""

    def __init__(self, period_repository: PeriodRepository, clock: Clock | None = None) -> None:
        """Construye el caso de uso.

        Args:
            period_repository: acceso a los períodos de matrícula.
            clock: fuente de la hora actual. Se puede sustituir en los tests para comprobar
                los bordes de la ventana —el primer y el último segundo— sin esperar a que
                lleguen de verdad.
        """
        self._period_repository = period_repository
        self._clock = clock or _reloj_del_sistema

    def execute(self) -> CurrentPeriodDTO:
        """Consulta la ventana de matrícula vigente.

        Distingue dos estados que el frontend necesita separar: que exista un período activo y
        que ese período admita inscripciones **ahora**. Un período activado cuya fecha de
        apertura aún no ha llegado devuelve `is_open = False`, y eso permite mostrar "la
        matrícula abre el martes" en lugar de un escueto "no hay período".

        Returns:
            El período con su estado y su cuenta atrás.

        Raises:
            NoActivePeriodError: si no hay ninguna ventana activa.
        """
        periodo = self._period_repository.find_active()

        if periodo is None:
            raise NoActivePeriodError()

        ahora = self._clock()

        return CurrentPeriodDTO(
            period=periodo,
            is_open=periodo.is_open(ahora),
            time_remaining_seconds=periodo.time_remaining_seconds(ahora),
        )
