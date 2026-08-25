"""Pruebas del plan de estudios (iteración 6.1).

El plan responde «qué materias son las mías», que el catálogo no puede contestar. Lo que se
comprueba aquí es que responde SOLO por la carrera del estudiante y que trae los dos datos que
no viven en la materia: el semestre sugerido y la obligatoriedad.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.application.use_cases.catalog.get_study_plan import GetStudyPlanUseCase
from app.domain.exceptions.authentication import StudentProfileNotFoundError
from app.domain.exceptions.catalog import ProgramNotFoundError
from tests.unit.doubles import (
    InMemoryCourseRepository,
    InMemoryProgramRepository,
    InMemoryStudentRepository,
)
from tests.unit.factories import crear_estudiante, crear_materia, crear_programa


def _montar():
    """Dos carreras con planes distintos, y un estudiante en la primera.

    Física aparece en las DOS: es lo que permite comprobar que una materia compartida entre
    programas puede tener semestre distinto en cada uno, que es justo la razón de que el
    semestre viva en la relación y no en la materia.
    """
    sistemas = crear_programa(code="ISIS", name="Ingeniería de Sistemas", total_semesters=10)
    derecho = crear_programa(code="DERE", name="Derecho", total_semesters=8)

    calculo = crear_materia(code="MAT101", name="Cálculo I", credits=4)
    programacion = crear_materia(code="PRG101", name="Programación I", credits=3)
    fisica = crear_materia(code="FIS101", name="Física I", credits=3)
    constitucional = crear_materia(code="DER101", name="Derecho Constitucional", credits=4)

    materias = InMemoryCourseRepository(
        [calculo, programacion, fisica, constitucional],
        plan={
            # Desordenado a propósito: el caso de uso debe ordenarlo.
            sistemas.id: [(fisica.id, 2), (programacion.id, 1), (calculo.id, 1)],
            # Física también está en Derecho, pero en otro semestre.
            derecho.id: [(constitucional.id, 1), (fisica.id, 4)],
        },
    )

    estudiante = crear_estudiante(program_id=sistemas.id)

    caso = GetStudyPlanUseCase(
        InMemoryStudentRepository([estudiante]),
        InMemoryProgramRepository([sistemas, derecho]),
        materias,
    )

    return caso, estudiante, derecho


@pytest.mark.unit
def test_el_plan_trae_solo_las_materias_de_la_carrera() -> None:
    """Es el arreglo de fondo: antes el catálogo mostraba las de todas las carreras."""
    caso, estudiante, _ = _montar()

    plan = caso.execute(estudiante.id)

    codigos = [e.course.code.value for e in plan.entries]
    assert codigos == ["MAT101", "PRG101", "FIS101"]
    # Derecho Constitucional es de otra carrera y no aparece.
    assert "DER101" not in codigos


@pytest.mark.unit
def test_el_plan_llega_ordenado_por_semestre_y_luego_por_codigo() -> None:
    """Es como se lee un plan de estudios: por semestres, de primero a último."""
    caso, estudiante, _ = _montar()

    plan = caso.execute(estudiante.id)

    semestres = [e.suggested_semester for e in plan.entries]
    assert semestres == sorted(semestres)
    # Dentro del primer semestre, alfabético por código: MAT101 antes que PRG101.
    primero = [e.course.code.value for e in plan.entries if e.suggested_semester == 1]
    assert primero == ["MAT101", "PRG101"]


@pytest.mark.unit
def test_una_materia_compartida_lleva_el_semestre_de_cada_carrera() -> None:
    """Es la razón de que el semestre viva en la relación y no en la materia.

    Física es de segundo en Ingeniería y de cuarto en Derecho. Si el dato estuviera en la
    entidad `Course`, una de las dos carreras tendría que mentir.
    """
    caso, estudiante, _ = _montar()

    plan = caso.execute(estudiante.id)

    fisica = next(e for e in plan.entries if e.course.code.value == "FIS101")
    assert fisica.suggested_semester == 2


@pytest.mark.unit
def test_el_plan_suma_sus_creditos() -> None:
    caso, estudiante, _ = _montar()

    plan = caso.execute(estudiante.id)

    # 4 + 3 + 3.
    assert plan.total_credits == 10


@pytest.mark.unit
def test_el_plan_identifica_el_programa() -> None:
    caso, estudiante, _ = _montar()

    plan = caso.execute(estudiante.id)

    assert plan.program_code == "ISIS"
    assert plan.program_name == "Ingeniería de Sistemas"
    # La duración permite mostrar los semestres que aún no tienen materias cargadas.
    assert plan.total_semesters == 10


@pytest.mark.unit
def test_un_programa_sin_plan_cargado_devuelve_una_lista_vacia() -> None:
    """Es un estado legítimo mientras Registro Académico no lo carga, no un error."""
    programa = crear_programa(code="NUE", name="Programa Nuevo")
    estudiante = crear_estudiante(program_id=programa.id)

    caso = GetStudyPlanUseCase(
        InMemoryStudentRepository([estudiante]),
        InMemoryProgramRepository([programa]),
        InMemoryCourseRepository([]),
    )

    plan = caso.execute(estudiante.id)

    assert plan.entries == []
    assert plan.total_credits == 0


@pytest.mark.unit
def test_una_cuenta_sin_perfil_academico_no_tiene_plan() -> None:
    caso, _, _ = _montar()

    with pytest.raises(StudentProfileNotFoundError):
        caso.execute(uuid4())


@pytest.mark.unit
def test_falla_si_el_programa_del_estudiante_ya_no_existe() -> None:
    """Solo puede darse si se borra un programa con estudiantes activos.

    Se modela igualmente: dejar que el `None` llegue a la pantalla produciría un plan con el
    nombre del programa en blanco, que es peor que un error explicado.
    """
    estudiante = crear_estudiante(program_id=uuid4())

    caso = GetStudyPlanUseCase(
        InMemoryStudentRepository([estudiante]),
        InMemoryProgramRepository([]),
        InMemoryCourseRepository([]),
    )

    with pytest.raises(ProgramNotFoundError):
        caso.execute(estudiante.id)
