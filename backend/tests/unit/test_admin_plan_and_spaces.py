"""Pruebas de la edición del plan de estudios y del alta de espacios (iteración 8.3).

Las dos operaciones tienen en común lo que las hace interesantes: **rechazan cosas que la base
de datos aceptaría en silencio**. Un código de aula en minúsculas crearía una segunda fila para
el mismo salón; sacar una materia del plan borraría en cascada los requisitos que la nombran.
Ninguno de los dos daría error, y por eso hay que impedirlos antes de llegar a la base.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.application.use_cases.admin.manage_spaces import CreateSpaceUseCase, ListSpacesUseCase
from app.application.use_cases.admin.manage_study_plan import (
    GetProgramStudyPlanUseCase,
    RemovePlanCourseUseCase,
    SetPlanCourseUseCase,
)
from app.domain.exceptions.admin import CourseRequiredByOthersError, DuplicateSpaceCodeError
from app.domain.exceptions.catalog import CourseNotFoundError, ProgramNotFoundError
from app.domain.value_objects.space_type import SpaceType
from tests.unit.doubles import (
    FakeUnitOfWork,
    InMemoryCourseRepository,
    InMemoryProgramRepository,
    InMemorySpaceRepository,
)
from tests.unit.factories import crear_espacio, crear_materia, crear_programa

# ---------------------------------------------------------------------------
# Alta de espacios
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_el_codigo_del_espacio_se_guarda_normalizado() -> None:
    """Sin normalizar, `a-201` y `A-201` serían dos aulas distintas para la base.

    Y con dos filas para el mismo salón, la restricción de doble reserva de la 7.2 no puede
    impedir nada: cree que son sitios diferentes. Es el problema que la 7.1 vino a resolver,
    volviendo por la puerta de atrás.
    """
    inventario = InMemorySpaceRepository()

    creado = CreateSpaceUseCase(inventario, FakeUnitOfWork()).execute(
        code="  a-201 ", space_type=SpaceType.CLASSROOM
    )

    assert creado.code == "A-201"
    assert inventario.find_by_code("A-201") is not None


@pytest.mark.unit
def test_no_se_puede_dar_de_alta_dos_veces_el_mismo_espacio() -> None:
    inventario = InMemorySpaceRepository([crear_espacio(code="A-201")])

    with pytest.raises(DuplicateSpaceCodeError) as error:
        CreateSpaceUseCase(inventario, FakeUnitOfWork()).execute(
            code="a-201", space_type=SpaceType.CLASSROOM
        )

    assert error.value.details["code"] == "A-201"


@pytest.mark.unit
def test_un_espacio_puede_nacer_sin_aforo() -> None:
    # Un aula cuyo aforo nadie ha medido es un dato legítimo. Forzar un número inventaría la
    # cifra contra la que la 7.2 valida que un grupo quepa.
    creado = CreateSpaceUseCase(InMemorySpaceRepository(), FakeUnitOfWork()).execute(
        code="LAB-09", space_type=SpaceType.LABORATORY
    )

    assert creado.capacity is None
    assert creado.fits(100) is None


@pytest.mark.unit
def test_el_inventario_se_puede_filtrar_por_tipo() -> None:
    inventario = InMemorySpaceRepository(
        [
            crear_espacio(code="A-201", space_type=SpaceType.CLASSROOM),
            crear_espacio(code="LAB-01", space_type=SpaceType.LABORATORY),
        ]
    )

    encontrados = ListSpacesUseCase(inventario).execute(space_type=SpaceType.LABORATORY)

    assert [e.code for e in encontrados] == ["LAB-01"]


# ---------------------------------------------------------------------------
# Edición del plan de estudios
# ---------------------------------------------------------------------------


def _plan():
    """Un programa con dos materias, donde la segunda exige la primera."""
    programa = crear_programa(code="ISIS")
    calculo_i = crear_materia(code="MAT101")
    calculo_ii = crear_materia(code="MAT102")

    catalogo = InMemoryCourseRepository(
        [calculo_i, calculo_ii],
        prerequisites={calculo_ii.id: [calculo_i]},
        plan={programa.id: [(calculo_i.id, 1), (calculo_ii.id, 2)]},
    )

    return programa, calculo_i, calculo_ii, catalogo


@pytest.mark.unit
def test_poner_una_materia_en_el_plan_la_deja_ahi() -> None:
    programa, _, _, catalogo = _plan()
    nueva = crear_materia(code="PRG101")
    catalogo.save(nueva)

    SetPlanCourseUseCase(
        InMemoryProgramRepository([programa]), catalogo, FakeUnitOfWork()
    ).execute(
        program_id=programa.id, course_id=nueva.id, suggested_semester=1, is_mandatory=True
    )

    assert nueva.id in {c.id for c, _, _ in catalogo.find_study_plan(programa.id)}


@pytest.mark.unit
def test_volver_a_ponerla_actualiza_en_vez_de_duplicar() -> None:
    """`PUT` idempotente: la clave del plan es la pareja (programa, materia).

    Si añadir y editar fueran operaciones distintas, quien administra tendría que saber de
    antemano cuál pedir, y la interfaz consultarlo antes de cada guardado para acertar.
    """
    programa, calculo_i, _, catalogo = _plan()
    caso = SetPlanCourseUseCase(
        InMemoryProgramRepository([programa]), catalogo, FakeUnitOfWork()
    )

    caso.execute(
        program_id=programa.id, course_id=calculo_i.id, suggested_semester=3, is_mandatory=False
    )

    plan = catalogo.find_study_plan(programa.id)
    assert len([c for c, _, _ in plan if c.id == calculo_i.id]) == 1
    assert next(s for c, s, _ in plan if c.id == calculo_i.id) == 3


@pytest.mark.unit
def test_no_se_puede_poner_una_materia_en_un_programa_que_no_existe() -> None:
    _, calculo_i, _, catalogo = _plan()

    with pytest.raises(ProgramNotFoundError):
        SetPlanCourseUseCase(
            InMemoryProgramRepository([]), catalogo, FakeUnitOfWork()
        ).execute(
            program_id=uuid4(), course_id=calculo_i.id, suggested_semester=1, is_mandatory=True
        )


@pytest.mark.unit
def test_sacar_del_plan_una_materia_que_otras_exigen_se_rechaza() -> None:
    """Es la razón de ser de este caso de uso.

    La clave foránea de los requisitos apunta al plan con `ON DELETE CASCADE`, así que sacar
    `MAT101` borraría en silencio el requisito «`MAT102` exige `MAT101`». Nadie se enteraría
    hasta que alguien inscribiera Cálculo II sin haber visto Cálculo I.
    """
    programa, calculo_i, _, catalogo = _plan()

    with pytest.raises(CourseRequiredByOthersError) as error:
        RemovePlanCourseUseCase(catalogo, FakeUnitOfWork()).execute(
            program_id=programa.id, course_id=calculo_i.id
        )

    assert error.value.details["required_by"] == ["MAT102"]


@pytest.mark.unit
def test_sacar_una_materia_que_nadie_exige_funciona() -> None:
    programa, _, calculo_ii, catalogo = _plan()

    RemovePlanCourseUseCase(catalogo, FakeUnitOfWork()).execute(
        program_id=programa.id, course_id=calculo_ii.id
    )

    assert calculo_ii.id not in {c.id for c, _, _ in catalogo.find_study_plan(programa.id)}


@pytest.mark.unit
def test_sacar_una_materia_que_no_estaba_responde_que_no_existe() -> None:
    # Confirmar una operación que no hizo nada esconde el malentendido de quien la pidió.
    programa, _, _, catalogo = _plan()

    with pytest.raises(CourseNotFoundError):
        RemovePlanCourseUseCase(catalogo, FakeUnitOfWork()).execute(
            program_id=programa.id, course_id=uuid4()
        )


@pytest.mark.unit
def test_el_plan_de_administracion_no_trae_semaforo() -> None:
    """Aquí se edita la carrera, no se consulta el avance de nadie.

    El semáforo cruza el plan con el historial y la matrícula de una persona concreta, y en
    esta pantalla no hay persona.
    """
    programa, _, _, catalogo = _plan()

    plan = GetProgramStudyPlanUseCase(
        InMemoryProgramRepository([programa]), catalogo
    ).execute(programa.id)

    assert plan.program_code == "ISIS"
    assert len(plan.entries) == 2
    assert plan.approved_credits == 0
