"""Pruebas de la edición de requisitos del plan (iteración 8.3, fase B).

**Los requisitos son retroactivos y el plan no se versiona.** Esa decisión salió de cómo se leen
los dos tipos, no de una preferencia, y estas pruebas fijan justamente esa asimetría:

- Un **prerrequisito** solo se valida al inscribir. Creada la inscripción, nadie vuelve a
  comprobarlo, así que una regla nueva no puede romper una matrícula existente: no hay víctima.
- Un **correquisito** se recalcula en cada lectura de las inscripciones del período activo, y ahí
  sí puede dejar a alguien incompleto.

De ahí sale la única restricción que hace falta, y la marca la VENTANA, no el tipo de cambio: con
la ventana abierta el estudiante ve el pendiente y lo resuelve inscribiendo lo que falta; con la
ventana cerrada ve que le falta algo y no puede inscribir nada. Solo ese caso se rechaza.

Aparte va el ciclo imposible, que es el error más silencioso de todos: la base acepta cada fila
por separado y las materias del ciclo quedan ininscribibles para siempre sin que nada avise.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.application.use_cases.admin.manage_study_plan import (
    RemoveRequirementUseCase,
    SetRequirementUseCase,
)
from app.domain.exceptions.admin import (
    ImpossibleRequirementCycleError,
    RequirementWouldTrapEnrolledError,
)
from app.domain.exceptions.catalog import CourseNotFoundError, ProgramNotFoundError
from app.domain.value_objects.requirement_type import RequirementType
from tests.unit.doubles import (
    FakeUnitOfWork,
    InMemoryCourseRepository,
    InMemoryEnrollmentRepository,
    InMemoryPeriodRepository,
    InMemoryProgramRepository,
)
from tests.unit.factories import crear_materia, crear_periodo, crear_programa

AHORA = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)


def _plan(*, prerequisites=None, corequisites=None):
    """Un programa con tres materias y ningún requisito, salvo los que pida el test."""
    programa = crear_programa(code="ISIS")
    calculo_i = crear_materia(code="MAT101")
    calculo_ii = crear_materia(code="MAT102")
    fisica = crear_materia(code="FIS101")

    catalogo = InMemoryCourseRepository(
        [calculo_i, calculo_ii, fisica],
        prerequisites=prerequisites or {},
        corequisites=corequisites or {},
        plan={programa.id: [(calculo_i.id, 1), (calculo_ii.id, 2), (fisica.id, 2)]},
    )

    return programa, calculo_i, calculo_ii, fisica, catalogo


def _caso(programa, catalogo, *, periodo=None, inscritos=None):
    return SetRequirementUseCase(
        InMemoryProgramRepository([programa]),
        catalogo,
        InMemoryEnrollmentRepository(inscritos_por_materia=inscritos or {}),
        InMemoryPeriodRepository([periodo] if periodo else []),
        FakeUnitOfWork(),
        clock=lambda: AHORA,
    )


# ---------------------------------------------------------------------------
# Cargar y quitar
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_cargar_un_prerrequisito_lo_deja_en_el_plan() -> None:
    programa, calculo_i, calculo_ii, _, catalogo = _plan()

    _caso(programa, catalogo).execute(
        program_id=programa.id,
        course_id=calculo_ii.id,
        required_course_id=calculo_i.id,
        requirement_type=RequirementType.PREREQUISITE,
    )

    requisitos = catalogo.find_requirements(calculo_ii.id, programa.id)
    assert [(r.course.code.value, r.requirement_type) for r in requisitos] == [
        ("MAT101", RequirementType.PREREQUISITE)
    ]


@pytest.mark.unit
def test_volver_a_cargarlo_con_otro_tipo_lo_cambia_en_vez_de_duplicarlo() -> None:
    """La clave de la tabla es la terna y NO incluye el tipo.

    Ese diseño es el que impide declarar que una materia es a la vez prerrequisito y
    correquisito de otra: dos reglas que se contradicen —una exige haberla terminado, la otra
    exige estar cursándola— y que dejarían la materia ininscribible sin que nada avisara.
    """
    programa, calculo_i, calculo_ii, _, catalogo = _plan()
    caso = _caso(programa, catalogo)

    caso.execute(
        program_id=programa.id,
        course_id=calculo_ii.id,
        required_course_id=calculo_i.id,
        requirement_type=RequirementType.PREREQUISITE,
    )
    caso.execute(
        program_id=programa.id,
        course_id=calculo_ii.id,
        required_course_id=calculo_i.id,
        requirement_type=RequirementType.COREQUISITE,
    )

    requisitos = catalogo.find_requirements(calculo_ii.id, programa.id)
    assert len(requisitos) == 1
    assert requisitos[0].is_corequisite()


@pytest.mark.unit
def test_no_se_puede_exigir_una_materia_que_no_esta_en_ese_plan() -> None:
    """Es el error más probable al cargar un plan: exigir una materia de otra carrera.

    Se comprueba en el caso de uso y no se deja a la clave foránea compuesta porque un fallo de
    restricción no dice CUÁL de las dos materias falta, y quien administra tendría que adivinar.
    """
    programa, calculo_i, _, _, catalogo = _plan()
    ajena = crear_materia(code="DER101")
    catalogo.save(ajena)

    with pytest.raises(CourseNotFoundError):
        _caso(programa, catalogo).execute(
            program_id=programa.id,
            course_id=calculo_i.id,
            required_course_id=ajena.id,
            requirement_type=RequirementType.PREREQUISITE,
        )


@pytest.mark.unit
def test_no_se_puede_cargar_un_requisito_en_un_programa_que_no_existe() -> None:
    _, calculo_i, calculo_ii, _, catalogo = _plan()

    caso = SetRequirementUseCase(
        InMemoryProgramRepository([]),
        catalogo,
        InMemoryEnrollmentRepository(),
        InMemoryPeriodRepository([]),
        FakeUnitOfWork(),
        clock=lambda: AHORA,
    )

    with pytest.raises(ProgramNotFoundError):
        caso.execute(
            program_id=uuid4(),
            course_id=calculo_ii.id,
            required_course_id=calculo_i.id,
            requirement_type=RequirementType.PREREQUISITE,
        )


@pytest.mark.unit
def test_quitar_un_requisito_que_no_estaba_responde_que_no_existe() -> None:
    programa, calculo_i, calculo_ii, _, catalogo = _plan()

    with pytest.raises(CourseNotFoundError):
        RemoveRequirementUseCase(catalogo, FakeUnitOfWork()).execute(
            program_id=programa.id,
            course_id=calculo_ii.id,
            required_course_id=calculo_i.id,
        )


@pytest.mark.unit
def test_quitar_un_requisito_no_comprueba_matriculados() -> None:
    """Relajar una regla no puede dejar a nadie incompleto, así que no necesita defensa.

    Quien ya cumplía el requisito sigue cumpliendo el plan; quien no lo cumplía deja de estar
    bloqueado. Es la asimetría que justifica que este caso de uso no reciba ni las inscripciones
    ni los períodos.
    """
    programa, calculo_i, _, fisica, catalogo = _plan()
    catalogo.save_requirement(
        program_id=programa.id,
        course_id=fisica.id,
        required_course_id=calculo_i.id,
        requirement_type=RequirementType.COREQUISITE,
    )

    RemoveRequirementUseCase(catalogo, FakeUnitOfWork()).execute(
        program_id=programa.id, course_id=fisica.id, required_course_id=calculo_i.id
    )

    assert catalogo.find_requirements(fisica.id, programa.id) == []


# ---------------------------------------------------------------------------
# Ciclos imposibles
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_un_ciclo_de_prerrequisitos_se_rechaza() -> None:
    """Sin esto las dos materias quedan ininscribibles para siempre y nada avisa.

    La base acepta cada fila por separado, el validador las rechaza una a una sin poder decir
    por qué, y el semáforo las pinta bloqueadas sin salida. El error aparece meses después,
    cuando un estudiante se queda atascado.
    """
    programa, calculo_i, calculo_ii, _, catalogo = _plan()
    caso = _caso(programa, catalogo)

    caso.execute(
        program_id=programa.id,
        course_id=calculo_ii.id,
        required_course_id=calculo_i.id,
        requirement_type=RequirementType.PREREQUISITE,
    )

    with pytest.raises(ImpossibleRequirementCycleError) as error:
        caso.execute(
            program_id=programa.id,
            course_id=calculo_i.id,
            required_course_id=calculo_ii.id,
            requirement_type=RequirementType.PREREQUISITE,
        )

    assert error.value.details["cycle"] == ["MAT101", "MAT102", "MAT101"]


@pytest.mark.unit
def test_el_ciclo_se_detecta_aunque_pase_por_una_tercera_materia() -> None:
    # Mirar solo la pareja encontraría A->B->A y dejaría pasar A->B->C->A, que es igual de
    # imposible y bastante más fácil de cargar sin darse cuenta.
    programa, calculo_i, calculo_ii, fisica, catalogo = _plan()
    caso = _caso(programa, catalogo)

    caso.execute(
        program_id=programa.id,
        course_id=calculo_ii.id,
        required_course_id=calculo_i.id,
        requirement_type=RequirementType.PREREQUISITE,
    )
    caso.execute(
        program_id=programa.id,
        course_id=fisica.id,
        required_course_id=calculo_ii.id,
        requirement_type=RequirementType.PREREQUISITE,
    )

    with pytest.raises(ImpossibleRequirementCycleError) as error:
        caso.execute(
            program_id=programa.id,
            course_id=calculo_i.id,
            required_course_id=fisica.id,
            requirement_type=RequirementType.PREREQUISITE,
        )

    assert error.value.details["cycle"] == ["MAT101", "FIS101", "MAT102", "MAT101"]


@pytest.mark.unit
def test_un_ciclo_de_puros_correquisitos_es_legitimo() -> None:
    """«FIS101 y LAB101 se cursan juntas» es un ciclo mutuo, y es la forma normal de decirlo.

    Rechazarlo por ser un ciclo prohibiría el bloque que la iteración 6.2 construyó la exención
    de pares mutuos para poder inscribir. Lo que no se puede satisfacer es la mezcla.
    """
    programa, calculo_i, _, fisica, catalogo = _plan()
    caso = _caso(programa, catalogo)

    caso.execute(
        program_id=programa.id,
        course_id=fisica.id,
        required_course_id=calculo_i.id,
        requirement_type=RequirementType.COREQUISITE,
    )
    caso.execute(
        program_id=programa.id,
        course_id=calculo_i.id,
        required_course_id=fisica.id,
        requirement_type=RequirementType.COREQUISITE,
    )

    assert len(catalogo.find_requirements(calculo_i.id, programa.id)) == 1


@pytest.mark.unit
def test_una_materia_no_puede_exigirse_a_si_misma() -> None:
    programa, calculo_i, _, _, catalogo = _plan()

    with pytest.raises(ImpossibleRequirementCycleError):
        _caso(programa, catalogo).execute(
            program_id=programa.id,
            course_id=calculo_i.id,
            required_course_id=calculo_i.id,
            requirement_type=RequirementType.PREREQUISITE,
        )


# ---------------------------------------------------------------------------
# Retroactividad: el único caso con víctima
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_un_correquisito_nuevo_con_la_ventana_cerrada_se_rechaza() -> None:
    """Es el caso donde el estudiante queda atrapado sin remedio.

    Ve en su lista que le falta el correquisito y no puede inscribir nada para arreglarlo.
    Ninguna operación del sistema lo desatasca, y por eso el rechazo va aquí y no en un aviso.
    """
    programa, calculo_i, _, fisica, catalogo = _plan()
    cerrada = crear_periodo(
        is_active=True,
        starts_at=AHORA - timedelta(days=30),
        ends_at=AHORA - timedelta(days=1),
    )

    with pytest.raises(RequirementWouldTrapEnrolledError) as error:
        _caso(programa, catalogo, periodo=cerrada, inscritos={fisica.id: 12}).execute(
            program_id=programa.id,
            course_id=fisica.id,
            required_course_id=calculo_i.id,
            requirement_type=RequirementType.COREQUISITE,
        )

    assert error.value.details["enrolled_count"] == 12
    assert error.value.details["required_code"] == "MAT101"


@pytest.mark.unit
def test_con_la_ventana_abierta_el_mismo_correquisito_se_acepta() -> None:
    """Aquí el aviso ya existe y llega solo: el estudiante lo ve en `/mis-inscripciones`.

    Prohibirlo también con la ventana abierta impediría corregir un plan justo en el momento en
    que todavía se puede corregir sin coste para nadie.
    """
    programa, calculo_i, _, fisica, catalogo = _plan()
    abierta = crear_periodo(
        is_active=True,
        starts_at=AHORA - timedelta(days=1),
        ends_at=AHORA + timedelta(days=7),
    )

    _caso(programa, catalogo, periodo=abierta, inscritos={fisica.id: 12}).execute(
        program_id=programa.id,
        course_id=fisica.id,
        required_course_id=calculo_i.id,
        requirement_type=RequirementType.COREQUISITE,
    )

    assert catalogo.find_requirements(fisica.id, programa.id)[0].is_corequisite()


@pytest.mark.unit
def test_un_prerrequisito_nuevo_no_se_frena_aunque_haya_matriculados() -> None:
    """Es la asimetría que hizo innecesario versionar el plan de estudios.

    Los prerrequisitos se validan SOLO al inscribir; creada la inscripción, nadie vuelve a
    comprobarlos. Una regla nueva no puede romper una matrícula existente, así que frenar el
    cambio no protegería a nadie: solo impediría corregir el plan.
    """
    programa, calculo_i, _, fisica, catalogo = _plan()
    cerrada = crear_periodo(
        is_active=True,
        starts_at=AHORA - timedelta(days=30),
        ends_at=AHORA - timedelta(days=1),
    )

    _caso(programa, catalogo, periodo=cerrada, inscritos={fisica.id: 500}).execute(
        program_id=programa.id,
        course_id=fisica.id,
        required_course_id=calculo_i.id,
        requirement_type=RequirementType.PREREQUISITE,
    )

    assert catalogo.find_requirements(fisica.id, programa.id)[0].is_prerequisite()


@pytest.mark.unit
def test_sin_nadie_inscrito_el_correquisito_pasa_aunque_este_cerrada() -> None:
    # No hay a quién dejar incompleto. La regla protege personas, no prohíbe cambios.
    programa, calculo_i, _, fisica, catalogo = _plan()
    cerrada = crear_periodo(
        is_active=True,
        starts_at=AHORA - timedelta(days=30),
        ends_at=AHORA - timedelta(days=1),
    )

    _caso(programa, catalogo, periodo=cerrada, inscritos={}).execute(
        program_id=programa.id,
        course_id=fisica.id,
        required_course_id=calculo_i.id,
        requirement_type=RequirementType.COREQUISITE,
    )

    assert catalogo.find_requirements(fisica.id, programa.id)[0].is_corequisite()
