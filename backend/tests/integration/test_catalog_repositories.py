"""Pruebas de integración de los repositorios del catálogo.

Los tests unitarios comprueban la orquestación contra dobles en memoria; aquí se comprueba lo
único que esos dobles no pueden garantizar: que el SQL sea correcto. Filtros que se acumulan,
joins que no duplican filas, un total que corresponde con los elementos, y un número de
consultas que no crece con el número de resultados.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.domain.value_objects.course_code import CourseCode
from app.infrastructure.persistence.sqlalchemy.repositories.course_repository import (
    SQLAlchemyCourseRepository,
)
from app.infrastructure.persistence.sqlalchemy.repositories.offering_repository import (
    SQLAlchemyOfferingRepository,
)
from app.infrastructure.persistence.sqlalchemy.repositories.period_repository import (
    SQLAlchemyPeriodRepository,
)
from app.infrastructure.persistence.sqlalchemy.repositories.program_repository import (
    SQLAlchemyProgramRepository,
)
from tests.integration.conftest import CatalogoDePrueba

# ---------------------------------------------------------------------------
# ProgramRepository
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_program_find_by_id_returns_the_program(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    programa = SQLAlchemyProgramRepository(db_session).find_by_id(catalogo.program_id)

    assert programa is not None
    assert programa.name == "Ingeniería de Sistemas"


@pytest.mark.integration
def test_program_find_by_id_when_missing_returns_none(db_session: Session) -> None:
    assert SQLAlchemyProgramRepository(db_session).find_by_id(uuid4()) is None


# ---------------------------------------------------------------------------
# PeriodRepository
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_period_find_active_returns_only_the_active_one(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    # La fixture crea uno activo y uno cerrado.
    periodo = SQLAlchemyPeriodRepository(db_session).find_active()

    assert periodo is not None
    assert periodo.id == catalogo.period_id
    assert periodo.is_active is True


@pytest.mark.integration
def test_period_find_active_when_none_is_active_returns_none(db_session: Session) -> None:
    assert SQLAlchemyPeriodRepository(db_session).find_active() is None


# ---------------------------------------------------------------------------
# CourseRepository
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_course_find_by_code_matches_the_normalized_value(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    repo = SQLAlchemyCourseRepository(db_session)
    esperada = repo.find_by_id(catalogo.calculo_i_id)
    assert esperada is not None

    # El value object normaliza a mayúsculas, así que buscar en minúsculas debe encontrarla.
    encontrada = repo.find_by_code(CourseCode(esperada.code.value.lower()))

    assert encontrada is not None
    assert encontrada.id == catalogo.calculo_i_id


@pytest.mark.integration
def test_course_find_prerequisites_returns_the_direct_ones(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    prerrequisitos = SQLAlchemyCourseRepository(db_session).find_prerequisites(
        catalogo.calculo_ii_id
    )

    assert [p.id for p in prerrequisitos] == [catalogo.calculo_i_id]


@pytest.mark.integration
def test_course_find_prerequisites_when_there_are_none_returns_empty(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    assert SQLAlchemyCourseRepository(db_session).find_prerequisites(catalogo.calculo_i_id) == []


@pytest.mark.integration
def test_course_search_without_filters_returns_the_whole_catalog(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    # Física NO pertenece a ningún plan de estudios. Tiene que aparecer igualmente: si el
    # repositorio se uniera siempre a `program_courses`, desaparecería del catálogo completo.
    resultado = SQLAlchemyCourseRepository(db_session).search(page=1, size=20)

    assert resultado.total == 3
    assert catalogo.fisica_id in {c.id for c in resultado.items}


@pytest.mark.integration
def test_course_search_by_program_excludes_courses_outside_the_curriculum(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    resultado = SQLAlchemyCourseRepository(db_session).search(
        page=1, size=20, program_id=catalogo.program_id
    )

    assert {c.id for c in resultado.items} == {catalogo.calculo_i_id, catalogo.calculo_ii_id}
    assert resultado.total == 2


@pytest.mark.integration
def test_course_search_by_semester_filters_by_the_curriculum(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    resultado = SQLAlchemyCourseRepository(db_session).search(page=1, size=20, semester=2)

    assert [c.id for c in resultado.items] == [catalogo.calculo_ii_id]


@pytest.mark.integration
def test_course_search_combines_program_and_semester(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    resultado = SQLAlchemyCourseRepository(db_session).search(
        page=1, size=20, program_id=catalogo.program_id, semester=1
    )

    assert [c.id for c in resultado.items] == [catalogo.calculo_i_id]


@pytest.mark.integration
def test_course_search_by_text_is_case_insensitive_and_matches_the_name(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    resultado = SQLAlchemyCourseRepository(db_session).search(page=1, size=20, search="cÁlCuLo")

    assert {c.id for c in resultado.items} == {catalogo.calculo_i_id, catalogo.calculo_ii_id}


@pytest.mark.integration
@pytest.mark.parametrize("texto", ["calculo", "Calculo", "cálculo", "CÁLCULO", "cAlCuLo"])
def test_course_search_ignores_accents(
    db_session: Session, catalogo: CatalogoDePrueba, texto: str
) -> None:
    """Buscar "calculo" tiene que encontrar "Cálculo I".

    `ILIKE` normaliza mayúsculas pero no diacríticos, así que sin la extensión `unaccent` la
    búsqueda sin tilde devolvería cero resultados. En un catálogo en español, donde casi
    ningún estudiante escribe las tildes al buscar, eso dejaría inencontrables justo las
    materias más buscadas.
    """
    resultado = SQLAlchemyCourseRepository(db_session).search(page=1, size=20, search=texto)

    assert {c.id for c in resultado.items} == {catalogo.calculo_i_id, catalogo.calculo_ii_id}


@pytest.mark.integration
def test_course_search_by_text_also_matches_the_code(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    repo = SQLAlchemyCourseRepository(db_session)
    fisica = repo.find_by_id(catalogo.fisica_id)
    assert fisica is not None

    resultado = repo.search(page=1, size=20, search=fisica.code.value)

    assert [c.id for c in resultado.items] == [catalogo.fisica_id]


@pytest.mark.integration
def test_course_search_when_nothing_matches_returns_empty_page(db_session: Session) -> None:
    resultado = SQLAlchemyCourseRepository(db_session).search(
        page=1, size=20, search="materia-que-no-existe"
    )

    assert resultado.items == []
    assert resultado.total == 0


@pytest.mark.integration
def test_course_search_total_counts_all_matches_not_just_the_page(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    # El total es lo que le dice al frontend cuántas páginas hay. Que corresponda con el
    # filtro y no con el tamaño de página es la mitad del contrato de la paginación.
    resultado = SQLAlchemyCourseRepository(db_session).search(page=1, size=1)

    assert len(resultado.items) == 1
    assert resultado.total == 3


@pytest.mark.integration
def test_course_search_second_page_returns_different_courses(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    repo = SQLAlchemyCourseRepository(db_session)

    primera = repo.search(page=1, size=2)
    segunda = repo.search(page=2, size=2)

    assert len(primera.items) == 2
    assert len(segunda.items) == 1
    assert {c.id for c in primera.items}.isdisjoint({c.id for c in segunda.items})


@pytest.mark.integration
def test_course_search_by_program_does_not_duplicate_courses_in_several_curricula(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    # Una materia puede estar en el plan de varios programas. Sin `DISTINCT`, el join la
    # devolvería una vez por plan: el total quedaría inflado y la página repetiría filas.
    from app.infrastructure.persistence.sqlalchemy.models.program import ProgramModel
    from app.infrastructure.persistence.sqlalchemy.models.program_course import ProgramCourseModel

    otro_programa = ProgramModel(
        id=uuid4(), code=f"DER{uuid4().hex[:4].upper()}", name="Derecho", total_semesters=10
    )
    db_session.add(otro_programa)
    db_session.flush()
    db_session.add(
        ProgramCourseModel(
            program_id=otro_programa.id, course_id=catalogo.calculo_i_id, suggested_semester=1
        )
    )
    db_session.commit()

    resultado = SQLAlchemyCourseRepository(db_session).search(page=1, size=20, semester=1)

    assert [c.id for c in resultado.items] == [catalogo.calculo_i_id]
    assert resultado.total == 1


# ---------------------------------------------------------------------------
# OfferingRepository
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_offering_find_by_id_resolves_professor_and_schedule(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    grupo = SQLAlchemyOfferingRepository(db_session).find_by_id(catalogo.offering_grupo_01_id)

    assert grupo is not None
    assert grupo.professor is not None
    assert grupo.professor.full_name == "Ana Pérez"
    assert len(grupo.schedule) == 2
    assert grupo.available_slots() == 3


@pytest.mark.integration
def test_offering_schedule_comes_ordered_by_day_and_time(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    # La fixture inserta primero el miércoles y luego el lunes, a propósito.
    grupo = SQLAlchemyOfferingRepository(db_session).find_by_id(catalogo.offering_grupo_01_id)

    assert grupo is not None
    assert [f.day_of_week for f in grupo.schedule] == [1, 3]


@pytest.mark.integration
def test_offering_without_professor_or_schedule_is_still_returned(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    # Un `INNER JOIN` con `professors` haría desaparecer este grupo del catálogo en silencio.
    grupo = SQLAlchemyOfferingRepository(db_session).find_by_id(catalogo.offering_grupo_02_id)

    assert grupo is not None
    assert grupo.professor is None
    assert grupo.schedule == ()


@pytest.mark.integration
def test_offering_find_by_id_when_missing_returns_none(db_session: Session) -> None:
    assert SQLAlchemyOfferingRepository(db_session).find_by_id(uuid4()) is None


@pytest.mark.integration
def test_offering_find_by_course_and_period_returns_only_that_period(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    # La fixture crea un tercer grupo de la misma materia en un período cerrado.
    grupos = SQLAlchemyOfferingRepository(db_session).find_by_course_and_period(
        catalogo.calculo_i_id, catalogo.period_id
    )

    assert [g.group_number for g in grupos] == ["01", "02"]


@pytest.mark.integration
def test_offering_find_by_course_and_period_when_not_offered_returns_empty(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    grupos = SQLAlchemyOfferingRepository(db_session).find_by_course_and_period(
        catalogo.fisica_id, catalogo.period_id
    )

    assert grupos == []


@pytest.mark.integration
def test_offering_count_enrolled_reads_the_live_value(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    assert (
        SQLAlchemyOfferingRepository(db_session).count_enrolled(catalogo.offering_grupo_01_id) == 37
    )


@pytest.mark.integration
def test_offering_count_enrolled_when_missing_returns_none(db_session: Session) -> None:
    assert SQLAlchemyOfferingRepository(db_session).count_enrolled(uuid4()) is None


@pytest.mark.integration
def test_offering_query_count_does_not_grow_with_the_number_of_groups(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    """El test que protege contra el N+1.

    Es la regla que `SQLAlchemyOfferingRepository` promete en su docstring, y la que se rompe
    en cuanto alguien "simplifica" el repositorio recorriendo los grupos para pedir su
    horario. Con dos grupos el fallo pasaría desapercibido en cualquier otra prueba; en
    producción, con veinte grupos y cinco mil estudiantes consultando, no.
    """
    consultas: list[str] = []

    def registrar(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        consultas.append(statement)

    event.listen(db_session.get_bind(), "before_cursor_execute", registrar)
    try:
        grupos = SQLAlchemyOfferingRepository(db_session).find_by_course_and_period(
            catalogo.calculo_i_id, catalogo.period_id
        )
    finally:
        event.remove(db_session.get_bind(), "before_cursor_execute", registrar)

    assert len(grupos) == 2
    # Tres consultas fijas: los grupos, sus docentes y sus horarios. Nunca una por grupo.
    assert len(consultas) == 3, "\n\n".join(consultas)
