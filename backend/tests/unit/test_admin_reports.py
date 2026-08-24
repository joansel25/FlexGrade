"""Pruebas de los casos de uso de reportes de administración (iteración 4.4).

Los dos reportes no calculan nada por sí mismos: eligen el período activo, sellan la hora y
componen la respuesta con lo que devuelve el puerto. Eso es lo que se comprueba aquí. Que los
`GROUP BY` cuenten lo que deben se verifica contra PostgreSQL, en `test_admin_reports_api.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.dtos.report_dto import (
    OfferingOccupancyDTO,
    ProgramEnrollmentsDTO,
    ReportTotalsDTO,
)
from app.application.use_cases.admin.generate_enrollment_report import (
    GenerateEnrollmentReportUseCase,
)
from app.application.use_cases.admin.generate_occupancy_report import GenerateOccupancyReportUseCase
from app.domain.exceptions.catalog import NoActivePeriodError
from tests.unit.doubles import FakeReportReader, InMemoryPeriodRepository
from tests.unit.factories import crear_periodo


def _grupo(
    *, code: str = "MAT101", group: str = "01", capacity: int = 40, enrolled: int = 10
) -> OfferingOccupancyDTO:
    return OfferingOccupancyDTO(
        offering_id=uuid4(),
        course_code=code,
        course_name="Cálculo I",
        group_number=group,
        total_capacity=capacity,
        enrolled_count=enrolled,
    )


# ---------------------------------------------------------------------------
# Reporte de inscripciones
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_el_reporte_se_calcula_sobre_el_periodo_activo() -> None:
    """Ningún reporte recibe el período por parámetro: siempre es el activo."""
    activo = crear_periodo(code="2025-2-V1", is_active=True)
    cerrado = crear_periodo(code="2025-1-V1", is_active=False)
    reportes = FakeReportReader(
        totals=ReportTotalsDTO(total_enrollments=4832, unique_students=1245, active_offerings=87)
    )

    reporte = GenerateEnrollmentReportUseCase(
        reportes, InMemoryPeriodRepository([cerrado, activo])
    ).execute()

    assert reporte.period_code == "2025-2-V1"
    assert reporte.totals.total_enrollments == 4832
    assert set(reportes.periodos_consultados) == {activo.id}


@pytest.mark.unit
def test_el_reporte_sella_la_hora_de_calculo() -> None:
    """Un reporte sin fecha es un número sin contexto: no se sabe de cuándo es."""
    antes = datetime.now(UTC)

    reporte = GenerateEnrollmentReportUseCase(
        FakeReportReader(), InMemoryPeriodRepository([crear_periodo(is_active=True)])
    ).execute()

    assert antes <= reporte.generated_at <= datetime.now(UTC)


@pytest.mark.unit
def test_el_reporte_conserva_el_orden_del_desglose_por_programa() -> None:
    """El orden lo fija la consulta —de más a menos inscripciones— y el caso de uso no lo toca."""
    desglose = [
        ProgramEnrollmentsDTO(
            program_code="ISIS",
            program_name="Ingeniería de Sistemas",
            enrollments=1520,
            students=380,
        ),
        ProgramEnrollmentsDTO(
            program_code="DERE", program_name="Derecho", enrollments=310, students=95
        ),
    ]

    reporte = GenerateEnrollmentReportUseCase(
        FakeReportReader(by_program=desglose),
        InMemoryPeriodRepository([crear_periodo(is_active=True)]),
    ).execute()

    assert [p.program_code for p in reporte.by_program] == ["ISIS", "DERE"]


@pytest.mark.unit
def test_un_periodo_sin_inscripciones_devuelve_ceros_no_error() -> None:
    """Cero es una respuesta legítima: la ventana se abrió y todavía no entró nadie."""
    reporte = GenerateEnrollmentReportUseCase(
        FakeReportReader(), InMemoryPeriodRepository([crear_periodo(is_active=True)])
    ).execute()

    assert reporte.totals.total_enrollments == 0
    assert reporte.by_program == []


@pytest.mark.unit
def test_sin_periodo_activo_el_reporte_de_inscripciones_falla() -> None:
    """Devolver ceros haría creer que nadie se ha matriculado, y no es eso lo que ocurre."""
    with pytest.raises(NoActivePeriodError):
        GenerateEnrollmentReportUseCase(FakeReportReader(), InMemoryPeriodRepository()).execute()


# ---------------------------------------------------------------------------
# Reporte de ocupación
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_la_ocupacion_viaja_con_su_porcentaje_y_sus_cupos_libres() -> None:
    grupos = [_grupo(capacity=40, enrolled=37)]

    reporte = GenerateOccupancyReportUseCase(
        FakeReportReader(occupancy=grupos),
        InMemoryPeriodRepository([crear_periodo(is_active=True)]),
    ).execute(page=1, size=20)

    grupo = reporte.offerings[0]
    assert grupo.occupancy_rate == 92.5
    assert grupo.available_slots == 3


@pytest.mark.unit
def test_un_grupo_lleno_reporta_el_cien_por_ciento_y_cero_libres() -> None:
    reporte = GenerateOccupancyReportUseCase(
        FakeReportReader(occupancy=[_grupo(capacity=30, enrolled=30)]),
        InMemoryPeriodRepository([crear_periodo(is_active=True)]),
    ).execute(page=1, size=20)

    assert reporte.offerings[0].occupancy_rate == 100.0
    assert reporte.offerings[0].available_slots == 0


@pytest.mark.unit
def test_la_ocupacion_de_un_grupo_vacio_es_cero() -> None:
    reporte = GenerateOccupancyReportUseCase(
        FakeReportReader(occupancy=[_grupo(capacity=30, enrolled=0)]),
        InMemoryPeriodRepository([crear_periodo(is_active=True)]),
    ).execute(page=1, size=20)

    assert reporte.offerings[0].occupancy_rate == 0.0


@pytest.mark.unit
def test_el_reporte_de_ocupacion_pagina_y_conserva_el_total() -> None:
    """`total` es el de todo el período, no el de la página: es lo que dice cuántas quedan."""
    grupos = [_grupo(group=f"{n:02d}", enrolled=n) for n in range(1, 6)]

    reporte = GenerateOccupancyReportUseCase(
        FakeReportReader(occupancy=grupos),
        InMemoryPeriodRepository([crear_periodo(is_active=True)]),
    ).execute(page=2, size=2)

    assert len(reporte.offerings) == 2
    assert reporte.total == 5
    assert (reporte.page, reporte.size) == (2, 2)


@pytest.mark.unit
def test_sin_periodo_activo_el_reporte_de_ocupacion_falla() -> None:
    with pytest.raises(NoActivePeriodError):
        GenerateOccupancyReportUseCase(FakeReportReader(), InMemoryPeriodRepository()).execute(
            page=1, size=20
        )
