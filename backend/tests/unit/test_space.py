"""Pruebas de la entidad `Space` y de la resolución del aula al abrir un grupo (iteración 7.1).

El aula dejó de ser un texto dentro de la franja y pasó a ser una entidad. Lo que se comprueba
aquí es lo que ese cambio hace posible y lo que obliga a decidir: que un aforo desconocido no se
confunda con un «sí» ni con un «no», y que un código de aula que no existe falle al abrir el
grupo en vez de quedar guardado como una cadena que no significa nada.
"""

from __future__ import annotations

from datetime import time
from uuid import uuid4

import pytest

from app.application.use_cases.admin.create_course_offering import CreateCourseOfferingUseCase
from app.domain.exceptions.catalog import SpaceNotFoundError
from app.domain.value_objects.space_type import SpaceType
from tests.unit.doubles import (
    FakeUnitOfWork,
    InMemoryCourseRepository,
    InMemoryOfferingRepository,
    InMemoryPeriodRepository,
    InMemoryProfessorReader,
    InMemorySpaceRepository,
)
from tests.unit.factories import crear_espacio, crear_franja_pedida, crear_materia, crear_periodo

# ---------------------------------------------------------------------------
# El aforo desconocido
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_un_espacio_con_aforo_conocido_responde_si_cabe_el_grupo() -> None:
    aula = crear_espacio(capacity=40)

    assert aula.fits(40) is True
    assert aula.fits(41) is False


@pytest.mark.unit
def test_un_aforo_desconocido_no_es_ni_si_ni_no() -> None:
    """`None` y no `True` ni `False`, y la diferencia importa.

    Los espacios que la migración `0009` creó a partir de los textos existentes no traían aforo:
    en la cadena «A-201» no hay ningún número de sillas. Colapsar ese «no sé» en `True`
    aprobaría asignaciones que no caben; en `False` bloquearía aulas perfectamente utilizables
    solo porque nadie las ha medido. Quien llama decide qué hacer con la incertidumbre.
    """
    assert crear_espacio(capacity=None).fits(30) is None


@pytest.mark.unit
def test_un_espacio_sin_nombre_se_describe_por_su_codigo() -> None:
    # La mayoría de las aulas no se llaman de ninguna manera, solo se numeran.
    assert crear_espacio(code="A-201", name=None).describe() == "A-201"


@pytest.mark.unit
def test_un_espacio_con_nombre_propio_lo_incluye() -> None:
    aula = crear_espacio(
        code="LAB-01", name="Laboratorio de Redes", space_type=SpaceType.LABORATORY
    )

    assert aula.describe() == "LAB-01 (Laboratorio de Redes)"


# ---------------------------------------------------------------------------
# Resolución del aula al abrir un grupo
# ---------------------------------------------------------------------------


def _caso(*, espacios: list | None = None):
    """Monta el caso de uso de apertura de grupos con una materia y un período activos."""
    materia = crear_materia()
    periodo = crear_periodo(is_active=True)
    uow = FakeUnitOfWork()

    caso = CreateCourseOfferingUseCase(
        InMemoryOfferingRepository(),
        InMemoryCourseRepository([materia]),
        InMemoryPeriodRepository([periodo]),
        InMemoryProfessorReader(),
        InMemorySpaceRepository(espacios if espacios is not None else [crear_espacio()]),
        uow,
    )

    return caso, materia, uow


@pytest.mark.unit
def test_abrir_un_grupo_resuelve_el_codigo_del_aula_a_su_entidad() -> None:
    aula = crear_espacio(code="B-101", capacity=50)
    caso, materia, _ = _caso(espacios=[aula])

    creado = caso.execute(
        course_id=materia.id,
        group_number="01",
        total_capacity=30,
        schedule=[crear_franja_pedida(space_code="B-101")],
    )

    assert creado.schedule[0].space is not None
    assert creado.schedule[0].space.id == aula.id
    # El accesor de presentación sigue dando lo que la API expone bajo `classroom`.
    assert creado.schedule[0].classroom == "B-101"


@pytest.mark.unit
def test_abrir_un_grupo_con_un_aula_inexistente_falla_y_no_guarda_nada() -> None:
    """Antes esto se guardaba: cualquier cadena era un aula válida.

    Un texto que nadie reconoce no es un error visible, es un horario que dice que la clase es
    en un salón que no existe. Ahora falla al abrir el grupo, que es cuando alguien puede
    corregirlo.
    """
    caso, materia, uow = _caso(espacios=[crear_espacio(code="A-201")])

    with pytest.raises(SpaceNotFoundError) as error:
        caso.execute(
            course_id=materia.id,
            group_number="01",
            total_capacity=30,
            schedule=[crear_franja_pedida(space_code="NO-EXISTE")],
        )

    assert error.value.details["code"] == "NO-EXISTE"
    # Falla ANTES de abrir la transacción: no depende del estado del grupo.
    assert uow.entradas == 0


@pytest.mark.unit
def test_el_codigo_del_aula_no_distingue_mayusculas_ni_espacios() -> None:
    """Quien escribe `a-201 ` se refiere al mismo salón que quien escribe `A-201`.

    Obligarle a acertar el formato exacto convertiría un dato correcto en un 404.
    """
    aula = crear_espacio(code="A-201")
    caso, materia, _ = _caso(espacios=[aula])

    creado = caso.execute(
        course_id=materia.id,
        group_number="01",
        total_capacity=30,
        schedule=[crear_franja_pedida(space_code="  a-201 ")],
    )

    assert creado.schedule[0].space is not None
    assert creado.schedule[0].space.id == aula.id


@pytest.mark.unit
def test_una_franja_sin_aula_es_un_estado_legitimo() -> None:
    # El horario se publica antes de repartir los espacios.
    caso, materia, _ = _caso()

    creado = caso.execute(
        course_id=materia.id,
        group_number="01",
        total_capacity=30,
        schedule=[crear_franja_pedida(space_code=None)],
    )

    assert creado.schedule[0].space is None
    assert creado.schedule[0].classroom is None


@pytest.mark.unit
def test_el_mismo_aula_en_varias_franjas_se_busca_una_sola_vez() -> None:
    """Un grupo que se dicta lunes y miércoles en la misma aula son dos franjas y un espacio.

    Buscar el código una vez por franja sería una consulta de más por cada día de clase, sobre
    un dato que ya se tiene.
    """
    aula = crear_espacio(code="A-201")
    inventario = InMemorySpaceRepository([aula])
    materia = crear_materia()
    periodo = crear_periodo(is_active=True)

    consultas = {"n": 0}
    buscar_original = inventario.find_by_code

    def contando(code: str):
        consultas["n"] += 1
        return buscar_original(code)

    inventario.find_by_code = contando  # type: ignore[method-assign]

    CreateCourseOfferingUseCase(
        InMemoryOfferingRepository(),
        InMemoryCourseRepository([materia]),
        InMemoryPeriodRepository([periodo]),
        InMemoryProfessorReader(),
        inventario,
        FakeUnitOfWork(),
    ).execute(
        course_id=materia.id,
        group_number="01",
        total_capacity=30,
        schedule=[
            crear_franja_pedida(day_of_week=1, space_code="A-201"),
            crear_franja_pedida(day_of_week=3, space_code="A-201"),
            crear_franja_pedida(
                day_of_week=5, start_time=time(14, 0), end_time=time(16, 0), space_code="A-201"
            ),
        ],
    )

    assert consultas["n"] == 1
