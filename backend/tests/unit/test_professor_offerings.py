"""Pruebas de la carga docente (iteración 9.1).

El docente entra aquí como ACTOR, no como el dato del catálogo que era hasta la Fase 8. Lo que
se comprueba es sobre todo lo que la consulta **acota**:

- Solo sus grupos. El identificador sale del token y no hay parámetro con el que pedir los de
  otro, pero el caso de uso tiene que filtrar igual: la defensa del borde protege de una
  petición maliciosa, no de una consulta mal escrita.
- Solo el período activo. Devolver los quince semestres anteriores obligaría a la interfaz a
  filtrar lo que la consulta ya podía descartar.
- Sin período activo, lista vacía y no error: entre semestres no hay ventana abierta.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.application.use_cases.teaching.list_professor_offerings import (
    ListProfessorOfferingsUseCase,
)
from tests.unit.doubles import (
    InMemoryCourseRepository,
    InMemoryOfferingRepository,
    InMemoryPeriodRepository,
)
from tests.unit.factories import crear_materia, crear_oferta, crear_periodo, crear_profesor


def _escenario(*, con_periodo_activo: bool = True):
    """Dos docentes, dos períodos y cuatro grupos repartidos entre ellos."""
    ana = crear_profesor(full_name="Ana Pérez", email="ana@tdea.edu.co")
    beto = crear_profesor(full_name="Beto Ruiz", email="beto@tdea.edu.co")

    calculo = crear_materia(code="MAT101", name="Cálculo I")
    fisica = crear_materia(code="FIS101", name="Física I")

    activo = crear_periodo(code="2025-2-V1", is_active=con_periodo_activo)
    anterior = crear_periodo(code="2025-1-V1", is_active=False)

    grupos = [
        # De Ana, en el período activo. Se declaran en orden inverso al esperado para que el
        # test compruebe que ordena y no que los devuelve como los recibió.
        crear_oferta(
            enrollment_period_id=activo.id, course_id=fisica.id, group_number="02", professor=ana
        ),
        crear_oferta(
            enrollment_period_id=activo.id, course_id=calculo.id, group_number="01", professor=ana
        ),
        # De Ana, pero del semestre pasado.
        crear_oferta(
            enrollment_period_id=anterior.id,
            course_id=calculo.id,
            group_number="03",
            professor=ana,
        ),
        # De Beto, en el activo.
        crear_oferta(
            enrollment_period_id=activo.id, course_id=calculo.id, group_number="04", professor=beto
        ),
    ]

    caso = ListProfessorOfferingsUseCase(
        InMemoryOfferingRepository(grupos),
        InMemoryCourseRepository([calculo, fisica]),
        InMemoryPeriodRepository([activo, anterior]),
    )

    return caso, ana, beto


@pytest.mark.unit
def test_solo_devuelve_los_grupos_del_docente_que_pregunta() -> None:
    """La defensa del borde protege de una petición maliciosa, no de una consulta mal escrita.

    Que el identificador salga del token impide pedir la carga de otro; no impide que la
    consulta traiga de más si está mal filtrada.
    """
    caso, ana, _ = _escenario()

    carga = caso.execute(ana.id)

    assert [e.offering.group_number for e in carga.offerings] == ["01", "02"]


@pytest.mark.unit
def test_no_devuelve_los_grupos_de_periodos_anteriores() -> None:
    # Quien entra a calificar trabaja sobre el semestre en curso.
    caso, ana, _ = _escenario()

    carga = caso.execute(ana.id)

    assert "03" not in {e.offering.group_number for e in carga.offerings}
    assert carga.period_code == "2025-2-V1"


@pytest.mark.unit
def test_la_materia_viaja_resuelta_dentro_del_grupo() -> None:
    # Sin esto la interfaz recibiría un `course_id` y tendría que cruzarlo contra otra lista
    # para escribir el nombre.
    caso, ana, _ = _escenario()

    carga = caso.execute(ana.id)

    assert [e.course.code.value for e in carga.offerings] == ["MAT101", "FIS101"]


@pytest.mark.unit
def test_sin_periodo_activo_devuelve_vacio_y_no_falla() -> None:
    """Entre semestres no hay ventana abierta, y eso es normal.

    Un 404 diría que algo está roto cuando lo que pasa es que todavía no hay nada que dictar.
    `period_code` en `None` distingue este caso de «hay semestre y no tengo carga», que se ve
    igual y significa otra cosa.
    """
    caso, ana, _ = _escenario(con_periodo_activo=False)

    carga = caso.execute(ana.id)

    assert carga.offerings == []
    assert carga.period_code is None


@pytest.mark.unit
def test_un_docente_sin_carga_recibe_el_periodo_pero_ninguna_materia() -> None:
    caso, _, _ = _escenario()

    carga = caso.execute(uuid4())

    assert carga.offerings == []
    assert carga.period_code == "2025-2-V1"
