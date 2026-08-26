"""Pruebas unitarias de `ScheduleBlock`.

El solapamiento es la pieza que sostendrá la detección de choque de horarios en la Fase 3.
Un falso negativo permite que un estudiante quede inscrito en dos clases simultáneas; un
falso positivo le impide inscribir una materia que sí podía cursar. Ambos importan, y por
eso los bordes del intervalo están probados uno a uno.
"""

from __future__ import annotations

from datetime import time

import pytest

from app.domain.exceptions.invalid_value import InvalidScheduleBlockError
from app.domain.value_objects.schedule_block import ScheduleBlock
from tests.unit.factories import crear_espacio, crear_franja


@pytest.mark.unit
@pytest.mark.parametrize("dia", [0, 8, -1, 100])
def test_schedule_block_when_day_is_out_of_range_raises(dia: int) -> None:
    with pytest.raises(InvalidScheduleBlockError):
        crear_franja(day_of_week=dia)


@pytest.mark.unit
@pytest.mark.parametrize("dia", [1, 2, 3, 4, 5, 6, 7])
def test_schedule_block_when_day_is_within_iso_range_is_accepted(dia: int) -> None:
    assert crear_franja(day_of_week=dia).day_of_week == dia


@pytest.mark.unit
def test_schedule_block_when_end_is_before_start_raises() -> None:
    with pytest.raises(InvalidScheduleBlockError):
        crear_franja(start_time=time(10, 0), end_time=time(8, 0))


@pytest.mark.unit
def test_schedule_block_when_end_equals_start_raises() -> None:
    # Una clase de duración cero no es un horario, es un error de captura.
    with pytest.raises(InvalidScheduleBlockError):
        crear_franja(start_time=time(8, 0), end_time=time(8, 0))


@pytest.mark.unit
def test_overlaps_when_blocks_are_on_different_days_is_false() -> None:
    lunes = crear_franja(day_of_week=1, start_time=time(8, 0), end_time=time(10, 0))
    martes = crear_franja(day_of_week=2, start_time=time(8, 0), end_time=time(10, 0))

    assert lunes.overlaps(martes) is False


@pytest.mark.unit
def test_overlaps_when_blocks_are_identical_is_true() -> None:
    franja = crear_franja()

    assert franja.overlaps(crear_franja()) is True


@pytest.mark.unit
def test_overlaps_when_second_starts_inside_the_first_is_true() -> None:
    primera = crear_franja(start_time=time(8, 0), end_time=time(10, 0))
    segunda = crear_franja(start_time=time(9, 0), end_time=time(11, 0))

    assert primera.overlaps(segunda) is True


@pytest.mark.unit
def test_overlaps_when_one_contains_the_other_is_true() -> None:
    larga = crear_franja(start_time=time(8, 0), end_time=time(12, 0))
    corta = crear_franja(start_time=time(9, 0), end_time=time(10, 0))

    assert larga.overlaps(corta) is True


@pytest.mark.unit
def test_overlaps_when_blocks_are_consecutive_is_false() -> None:
    # El borde que importa: una clase termina a las 10:00 y la siguiente empieza a las 10:00.
    # No chocan. Tratarlo como conflicto bloquearia horarios perfectamente validos, que es el
    # error mas facil de cometer al implementar esto.
    primera = crear_franja(start_time=time(8, 0), end_time=time(10, 0))
    segunda = crear_franja(start_time=time(10, 0), end_time=time(12, 0))

    assert primera.overlaps(segunda) is False


@pytest.mark.unit
def test_overlaps_is_symmetric() -> None:
    # Si A choca con B, B tiene que chocar con A. Una implementacion que compare solo en un
    # sentido pasaria la mitad de los tests anteriores y aun asi estaria mal.
    primera = crear_franja(start_time=time(8, 0), end_time=time(10, 0))
    segunda = crear_franja(start_time=time(9, 0), end_time=time(11, 0))

    assert primera.overlaps(segunda) == segunda.overlaps(primera)


@pytest.mark.unit
def test_schedule_block_when_values_are_equal_instances_are_equal() -> None:
    # Es un value object: no tiene identidad, se compara por contenido.
    # El MISMO espacio en las dos: desde la iteración 7.1 el aula forma parte de la
    # identidad de la franja, y dos clases en salones distintos no son la misma clase.
    aula = crear_espacio()

    assert crear_franja(space=aula) == crear_franja(space=aula)


@pytest.mark.unit
def test_schedule_block_is_immutable() -> None:
    franja = crear_franja()

    with pytest.raises(AttributeError):
        franja.day_of_week = 3  # type: ignore[misc]


@pytest.mark.unit
def test_schedule_block_when_space_is_unknown_is_accepted() -> None:
    # El horario se publica antes de asignar aulas.
    assert ScheduleBlock(day_of_week=1, start_time=time(8, 0), end_time=time(10, 0)).classroom is (
        None
    )
