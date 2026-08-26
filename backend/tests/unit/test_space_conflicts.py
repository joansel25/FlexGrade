"""Pruebas de la doble reserva y el aforo (iteración 7.2).

Lo que se comprueba aquí es la PRIMERA de las dos defensas: la que da un mensaje útil. La que
garantiza que el estado imposible no pueda escribirse es la restricción de exclusión `GiST` de
la migración `0010`, y esa solo se puede probar contra PostgreSQL real —está en
`tests/integration/test_admin_catalog.py`—.

Las dos hacen falta. Sin la restricción, dos peticiones simultáneas comprueban a la vez que el
aula está libre y la reservan las dos. Sin esta validación, esa carrera perdida le llega a una
persona como un error de integridad y un 500.
"""

from __future__ import annotations

from datetime import time

import pytest

from app.application.use_cases.admin.create_course_offering import CreateCourseOfferingUseCase
from app.domain.exceptions.admin import SpaceCapacityExceededError, SpaceDoubleBookedError
from app.domain.services.space_conflict_detector import SpaceConflictDetector, SpaceReservation
from tests.unit.doubles import (
    FakeUnitOfWork,
    InMemoryCourseRepository,
    InMemoryOfferingRepository,
    InMemoryPeriodRepository,
    InMemoryProfessorReader,
    InMemorySpaceRepository,
)
from tests.unit.factories import (
    crear_espacio,
    crear_franja,
    crear_franja_pedida,
    crear_materia,
    crear_oferta,
    crear_periodo,
)

# ---------------------------------------------------------------------------
# Aforo
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_un_grupo_que_no_cabe_en_el_aula_se_rechaza() -> None:
    aula = crear_espacio(code="B-103", capacity=25)

    with pytest.raises(SpaceCapacityExceededError) as error:
        SpaceConflictDetector().ensure_fits(space=aula, total_capacity=40)

    assert error.value.details == {"space_code": "B-103", "capacity": 25, "required": 40}


@pytest.mark.unit
def test_un_grupo_que_cabe_justo_se_acepta() -> None:
    # 40 en un aula de 40 cabe: el límite es «no más de», no «menos de».
    SpaceConflictDetector().ensure_fits(space=crear_espacio(capacity=40), total_capacity=40)


@pytest.mark.unit
def test_un_aforo_desconocido_no_bloquea_la_asignacion() -> None:
    """Es una decisión consciente, no un descuido.

    Los espacios que nacieron del traslado de textos de la 7.1 no traen aforo. Tratar ese «no
    sé» como un «no cabe» inutilizaría aulas perfectamente válidas por una laguna del
    inventario, no por un problema real.
    """
    SpaceConflictDetector().ensure_fits(space=crear_espacio(capacity=None), total_capacity=500)


# ---------------------------------------------------------------------------
# Doble reserva
# ---------------------------------------------------------------------------


def _reserva(aula, *, day_of_week=1, start=time(8, 0), end=time(10, 0), grupo="02"):
    return SpaceReservation(
        space_id=aula.id,
        block=crear_franja(day_of_week=day_of_week, start_time=start, end_time=end, space=aula),
        course_code="MAT101",
        group_number=grupo,
    )


@pytest.mark.unit
def test_un_aula_ocupada_a_la_misma_hora_se_rechaza() -> None:
    aula = crear_espacio(code="A-201")
    candidata = crear_franja(day_of_week=1, start_time=time(9, 0), end_time=time(11, 0), space=aula)

    with pytest.raises(SpaceDoubleBookedError) as error:
        SpaceConflictDetector().ensure_free(candidate=candidata, reservations=[_reserva(aula)])

    detalles = error.value.details
    assert detalles["space_code"] == "A-201"
    # Dice QUIÉN la ocupa: «el aula está ocupada» deja buscando a ciegas.
    assert detalles["occupied_by"] == {"course_code": "MAT101", "group_number": "02"}


@pytest.mark.unit
def test_la_misma_aula_en_otro_dia_no_choca() -> None:
    aula = crear_espacio()
    candidata = crear_franja(day_of_week=3, space=aula)

    SpaceConflictDetector().ensure_free(
        candidate=candidata, reservations=[_reserva(aula, day_of_week=1)]
    )


@pytest.mark.unit
def test_clases_consecutivas_en_la_misma_aula_no_chocan() -> None:
    """Terminar a las 10:00 y empezar a las 10:00 es una clase seguida, no un conflicto.

    La restricción de la base usa un rango `[)` por la misma razón; si las dos reglas no
    coincidieran, una aceptaría lo que la otra rechaza.
    """
    aula = crear_espacio()
    candidata = crear_franja(start_time=time(10, 0), end_time=time(12, 0), space=aula)

    SpaceConflictDetector().ensure_free(candidate=candidata, reservations=[_reserva(aula)])


@pytest.mark.unit
def test_otra_aula_a_la_misma_hora_no_choca() -> None:
    ocupada = crear_espacio(code="A-201")
    libre = crear_espacio(code="B-101")
    candidata = crear_franja(space=libre)

    SpaceConflictDetector().ensure_free(candidate=candidata, reservations=[_reserva(ocupada)])


@pytest.mark.unit
def test_una_franja_sin_aula_no_le_quita_el_sitio_a_nadie() -> None:
    aula = crear_espacio()

    SpaceConflictDetector().ensure_free(
        candidate=crear_franja(space=None), reservations=[_reserva(aula)]
    )


# ---------------------------------------------------------------------------
# El caso de uso, que es quien las encadena
# ---------------------------------------------------------------------------


def _caso(*, aula, ocupado_por=None):
    """Monta la apertura de grupos con un aula y, opcionalmente, un grupo que ya la ocupa."""
    materia = crear_materia()
    periodo = crear_periodo(is_active=True)
    grupos = InMemoryOfferingRepository(ocupado_por or [])

    caso = CreateCourseOfferingUseCase(
        grupos,
        InMemoryCourseRepository([materia]),
        InMemoryPeriodRepository([periodo]),
        InMemoryProfessorReader(),
        InMemorySpaceRepository([aula]),
        FakeUnitOfWork(),
    )

    return caso, materia, periodo


@pytest.mark.unit
def test_abrir_un_grupo_en_un_aula_ya_ocupada_se_rechaza() -> None:
    aula = crear_espacio(code="A-201", capacity=50)
    periodo = crear_periodo(is_active=True)
    ocupante = crear_oferta(
        enrollment_period_id=periodo.id,
        group_number="01",
        schedule=(
            crear_franja(day_of_week=2, start_time=time(8, 0), end_time=time(10, 0), space=aula),
        ),
    )
    materia = crear_materia()

    caso = CreateCourseOfferingUseCase(
        InMemoryOfferingRepository([ocupante]),
        InMemoryCourseRepository([materia]),
        InMemoryPeriodRepository([periodo]),
        InMemoryProfessorReader(),
        InMemorySpaceRepository([aula]),
        FakeUnitOfWork(),
    )

    with pytest.raises(SpaceDoubleBookedError):
        caso.execute(
            course_id=materia.id,
            group_number="02",
            total_capacity=30,
            schedule=[
                crear_franja_pedida(
                    day_of_week=2, start_time=time(9, 0), end_time=time(11, 0), space_code="A-201"
                )
            ],
        )


@pytest.mark.unit
def test_abrir_un_grupo_que_no_cabe_en_el_aula_se_rechaza() -> None:
    aula = crear_espacio(code="B-103", capacity=25)
    caso, materia, _ = _caso(aula=aula)

    with pytest.raises(SpaceCapacityExceededError):
        caso.execute(
            course_id=materia.id,
            group_number="01",
            total_capacity=40,
            schedule=[crear_franja_pedida(space_code="B-103")],
        )


@pytest.mark.unit
def test_abrir_un_grupo_en_un_aula_libre_y_con_sitio_funciona() -> None:
    aula = crear_espacio(code="A-201", capacity=50)
    caso, materia, _ = _caso(aula=aula)

    creado = caso.execute(
        course_id=materia.id,
        group_number="01",
        total_capacity=40,
        schedule=[crear_franja_pedida(space_code="A-201")],
    )

    assert creado.schedule[0].classroom == "A-201"
