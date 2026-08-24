"""Caso de uso: reporte de ocupación por grupo del período activo."""

from __future__ import annotations

from datetime import UTC, datetime

from app.application.dtos.report_dto import OccupancyReportDTO
from app.application.ports.repositories.period_repository import PeriodRepository
from app.application.ports.repositories.report_repository import ReportReader
from app.domain.exceptions.catalog import NoActivePeriodError


class GenerateOccupancyReportUseCase:
    """Compone el reporte de ocupación de los grupos de la ventana activa.

    Es el reporte con el que se decide ampliar un cupo o abrir un grupo nuevo, y por eso llega
    ordenado del más lleno al más vacío: la primera página contiene justo los grupos sobre los
    que hay que actuar, sin tener que recorrer el resto.

    Como el de inscripciones, se calcula en vivo. La ocupación es el dato que más cambia
    durante la matrícula y `CLAUDE.md` es explícito: la disponibilidad de cupos nunca se cachea.
    """

    def __init__(self, reports: ReportReader, period_repository: PeriodRepository) -> None:
        self._reports = reports
        self._periods = period_repository

    def execute(self, *, page: int, size: int) -> OccupancyReportDTO:
        """Calcula el reporte.

        Args:
            page: número de página, empezando en 1.
            size: cuántos grupos por página.

        Returns:
            La página de grupos con su ocupación, y el total de grupos del período.

        Raises:
            NoActivePeriodError: si no hay ninguna ventana de matrícula activa.
        """
        periodo = self._periods.find_active()

        if periodo is None:
            raise NoActivePeriodError()

        pagina = self._reports.offering_occupancy(periodo.id, page=page, size=size)

        return OccupancyReportDTO(
            period_code=periodo.code,
            generated_at=datetime.now(UTC),
            offerings=pagina.items,
            total=pagina.total,
            page=pagina.page,
            size=pagina.size,
        )
