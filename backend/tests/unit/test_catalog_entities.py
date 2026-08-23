"""Pruebas unitarias de las entidades del catálogo: `EnrollmentPeriod` y `CourseOffering`.

Son las dos entidades del catálogo con comportamiento propio. `Course`, `Professor` y
`Program` transportan datos sin reglas asociadas todavía, y probar que una dataclass guarda
lo que se le pasa no aporta nada.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from tests.unit.factories import AHORA, crear_oferta, crear_periodo

# ---------------------------------------------------------------------------
# EnrollmentPeriod.is_open
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_period_when_active_and_within_dates_is_open() -> None:
    assert crear_periodo().is_open(AHORA) is True


@pytest.mark.unit
def test_period_when_not_activated_is_closed_even_within_dates() -> None:
    # Las fechas por si solas no abren la matricula: hace falta que un administrador la
    # active. Es lo que permite dejar un periodo preparado con antelacion.
    assert crear_periodo(is_active=False).is_open(AHORA) is False


@pytest.mark.unit
def test_period_when_active_but_not_started_yet_is_closed() -> None:
    periodo = crear_periodo(
        starts_at=AHORA + timedelta(days=1),
        ends_at=AHORA + timedelta(days=3),
    )

    assert periodo.is_open(AHORA) is False


@pytest.mark.unit
def test_period_when_active_but_already_ended_is_closed() -> None:
    periodo = crear_periodo(
        starts_at=AHORA - timedelta(days=3),
        ends_at=AHORA - timedelta(days=1),
    )

    assert periodo.is_open(AHORA) is False


@pytest.mark.unit
def test_period_at_the_exact_opening_instant_is_open() -> None:
    # El borde: quien llega en el primer segundo de la ventana tiene que poder entrar.
    periodo = crear_periodo(starts_at=AHORA, ends_at=AHORA + timedelta(days=1))

    assert periodo.is_open(AHORA) is True


@pytest.mark.unit
def test_period_at_the_exact_closing_instant_is_open() -> None:
    periodo = crear_periodo(starts_at=AHORA - timedelta(days=1), ends_at=AHORA)

    assert periodo.is_open(AHORA) is True


# ---------------------------------------------------------------------------
# EnrollmentPeriod.time_remaining_seconds
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_time_remaining_when_period_is_open_counts_down_to_the_close() -> None:
    periodo = crear_periodo(ends_at=AHORA + timedelta(hours=2))

    assert periodo.time_remaining_seconds(AHORA) == 7200


@pytest.mark.unit
def test_time_remaining_when_period_already_ended_is_zero_not_negative() -> None:
    # "Quedan -3.600 segundos" no significa nada para quien lo lee en la interfaz.
    periodo = crear_periodo(
        starts_at=AHORA - timedelta(days=2),
        ends_at=AHORA - timedelta(hours=1),
    )

    assert periodo.time_remaining_seconds(AHORA) == 0


# ---------------------------------------------------------------------------
# CourseOffering
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_available_slots_when_group_is_empty_equals_capacity() -> None:
    assert crear_oferta(total_capacity=40, enrolled_count=0).available_slots() == 40


@pytest.mark.unit
def test_available_slots_when_group_is_partially_filled_is_the_difference() -> None:
    assert crear_oferta(total_capacity=40, enrolled_count=37).available_slots() == 3


@pytest.mark.unit
def test_available_slots_when_group_is_exactly_full_is_zero() -> None:
    assert crear_oferta(total_capacity=40, enrolled_count=40).available_slots() == 0


@pytest.mark.unit
def test_available_slots_when_data_is_inconsistent_never_goes_negative() -> None:
    # El CHECK de PostgreSQL impide que esto llegue a ocurrir, pero la entidad no debe
    # depender de una garantia que vive fuera del dominio: un -2 propagado a la API se
    # mostraria al estudiante como cupos disponibles negativos.
    assert crear_oferta(total_capacity=40, enrolled_count=42).available_slots() == 0


@pytest.mark.unit
def test_is_full_when_there_is_one_slot_left_is_false() -> None:
    # El ultimo cupo es justo el que provoca la carrera de la Fase 3.
    assert crear_oferta(total_capacity=40, enrolled_count=39).is_full() is False


@pytest.mark.unit
def test_is_full_when_no_slots_remain_is_true() -> None:
    assert crear_oferta(total_capacity=40, enrolled_count=40).is_full() is True


@pytest.mark.unit
def test_offering_when_professor_is_unassigned_is_none() -> None:
    # Un grupo puede publicarse antes de asignar docente.
    assert crear_oferta().professor is None
