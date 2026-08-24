"""Caso de uso: reporte de inscripciones del período activo."""

from __future__ import annotations

from datetime import UTC, datetime

from app.application.dtos.report_dto import EnrollmentReportDTO
from app.application.ports.repositories.period_repository import PeriodRepository
from app.application.ports.repositories.report_repository import ReportReader
from app.domain.exceptions.catalog import NoActivePeriodError


class GenerateEnrollmentReportUseCase:
    """Compone el reporte de inscripciones de la ventana de matrícula activa.

    Es la herramienta que responde «cómo va la matrícula» mientras está ocurriendo, así que
    **no se cachea ni se precalcula**: una cifra de hace treinta segundos, servida justo cuando
    alguien decide si amplía un cupo, es peor que no tener el reporte, porque parece actual.

    Tampoco hay `UnitOfWork`: no escribe nada. Envolver dos lecturas en una transacción
    explícita solo añadiría ceremonia; SQLAlchemy ya las ejecuta dentro de la transacción
    implícita de la sesión de la petición, así que los totales y el desglose ven el mismo
    estado de la base de datos.
    """

    def __init__(self, reports: ReportReader, period_repository: PeriodRepository) -> None:
        self._reports = reports
        self._periods = period_repository

    def execute(self) -> EnrollmentReportDTO:
        """Calcula el reporte.

        Returns:
            Las cifras globales del período activo y su desglose por programa.

        Raises:
            NoActivePeriodError: si no hay ninguna ventana de matrícula activa. Sin período no
                hay reporte posible: devolver ceros haría creer que nadie se ha matriculado.
        """
        periodo = self._periods.find_active()

        if periodo is None:
            raise NoActivePeriodError()

        return EnrollmentReportDTO(
            period_code=periodo.code,
            # La hora se sella aquí y no en el router: es el instante en que se leyeron las
            # cifras, no aquel en que se serializó la respuesta.
            generated_at=datetime.now(UTC),
            totals=self._reports.enrollment_totals(periodo.id),
            by_program=self._reports.enrollments_by_program(periodo.id),
        )
