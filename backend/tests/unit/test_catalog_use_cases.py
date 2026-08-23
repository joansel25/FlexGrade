"""Pruebas unitarias de los casos de uso del catálogo.

Se ejecutan contra los dobles en memoria de `doubles.py`, sin base de datos. Comprueban la
ORQUESTACIÓN: qué se consulta, en qué orden, qué se devuelve y qué se rechaza. Que las
consultas SQL sean correctas lo verifican los tests de integración de cada adaptador.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

from app.application.use_cases.catalog.get_course_detail import GetCourseDetailUseCase
from app.application.use_cases.catalog.get_course_offerings import GetCourseOfferingsUseCase
from app.application.use_cases.catalog.get_current_period import GetCurrentPeriodUseCase
from app.application.use_cases.catalog.get_offering_detail import GetOfferingDetailUseCase
from app.application.use_cases.catalog.list_courses import ListCoursesUseCase
from app.domain.exceptions.catalog import (
    CourseNotFoundError,
    NoActivePeriodError,
    OfferingNotFoundError,
)
from tests.unit.doubles import (
    InMemoryCacheService,
    InMemoryCourseRepository,
    InMemoryOfferingRepository,
    InMemoryPeriodRepository,
)
from tests.unit.factories import AHORA, crear_materia, crear_oferta, crear_periodo

# Los tests de este archivo comprueban ORQUESTACION, no la politica de cache: usan una cache
# vacia y nueva en cada caso. El comportamiento de la cache se prueba en `test_catalog_cache.py`.
TTL = 30

# ---------------------------------------------------------------------------
# ListCoursesUseCase
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_list_courses_when_catalog_is_empty_returns_empty_page() -> None:
    caso = ListCoursesUseCase(InMemoryCourseRepository(), InMemoryCacheService(), TTL)

    resultado = caso.execute()

    assert resultado.items == []
    assert resultado.total == 0


@pytest.mark.unit
def test_list_courses_returns_courses_ordered_by_code() -> None:
    repo = InMemoryCourseRepository(
        [crear_materia(code="MAT201"), crear_materia(code="ALG101"), crear_materia(code="FIS101")]
    )

    resultado = ListCoursesUseCase(repo, InMemoryCacheService(), TTL).execute()

    assert [c.code.value for c in resultado.items] == ["ALG101", "FIS101", "MAT201"]


@pytest.mark.unit
def test_list_courses_when_page_size_exceeds_the_limit_is_capped() -> None:
    # Sin este techo, `?size=100000` seria una forma trivial de tumbar la base de datos
    # durante el pico de matricula.
    resultado = ListCoursesUseCase(InMemoryCourseRepository(), InMemoryCacheService(), TTL).execute(
        size=100_000
    )

    assert resultado.size == 100


@pytest.mark.unit
@pytest.mark.parametrize("pagina", [0, -5])
def test_list_courses_when_page_is_not_positive_falls_back_to_the_first(pagina: int) -> None:
    # Una pagina 0 o negativa produciria un OFFSET negativo, que en PostgreSQL es un error.
    resultado = ListCoursesUseCase(InMemoryCourseRepository(), InMemoryCacheService(), TTL).execute(
        page=pagina
    )

    assert resultado.page == 1


@pytest.mark.unit
def test_list_courses_when_size_is_not_positive_falls_back_to_one() -> None:
    resultado = ListCoursesUseCase(InMemoryCourseRepository(), InMemoryCacheService(), TTL).execute(
        size=0
    )

    assert resultado.size == 1


@pytest.mark.unit
def test_list_courses_reports_the_total_beyond_the_current_page() -> None:
    # El total es lo que permite al frontend saber cuantas paginas hay. Si devolviera solo
    # los elementos de la pagina, la paginacion se rompe en silencio.
    repo = InMemoryCourseRepository([crear_materia(code=f"MAT{i:03d}") for i in range(1, 26)])

    resultado = ListCoursesUseCase(repo, InMemoryCacheService(), TTL).execute(page=1, size=10)

    assert len(resultado.items) == 10
    assert resultado.total == 25


@pytest.mark.unit
def test_list_courses_when_searching_matches_name_case_insensitively() -> None:
    repo = InMemoryCourseRepository(
        [
            crear_materia(code="MAT101", name="Cálculo I"),
            crear_materia(code="FIS101", name="Física"),
        ]
    )

    resultado = ListCoursesUseCase(repo, InMemoryCacheService(), TTL).execute(search="cálculo")

    assert [c.code.value for c in resultado.items] == ["MAT101"]


# ---------------------------------------------------------------------------
# GetCourseDetailUseCase
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_course_detail_when_course_does_not_exist_raises() -> None:
    caso = GetCourseDetailUseCase(InMemoryCourseRepository(), InMemoryCacheService(), TTL)

    with pytest.raises(CourseNotFoundError):
        caso.execute(uuid4())


@pytest.mark.unit
def test_get_course_detail_returns_the_course_with_its_prerequisites() -> None:
    calculo_i = crear_materia(code="MAT101", name="Cálculo I")
    calculo_ii = crear_materia(code="MAT102", name="Cálculo II")
    repo = InMemoryCourseRepository(
        [calculo_i, calculo_ii], prerequisites={calculo_ii.id: [calculo_i]}
    )

    resultado = GetCourseDetailUseCase(repo, InMemoryCacheService(), TTL).execute(calculo_ii.id)

    assert resultado.course.id == calculo_ii.id
    assert [c.code.value for c in resultado.prerequisites] == ["MAT101"]


@pytest.mark.unit
def test_get_course_detail_when_course_has_no_prerequisites_returns_empty_list() -> None:
    materia = crear_materia()
    repo = InMemoryCourseRepository([materia])

    assert (
        GetCourseDetailUseCase(repo, InMemoryCacheService(), TTL).execute(materia.id).prerequisites
        == []
    )


# ---------------------------------------------------------------------------
# GetCourseOfferingsUseCase
# ---------------------------------------------------------------------------


def _caso_de_grupos(
    cursos: InMemoryCourseRepository,
    grupos: InMemoryOfferingRepository,
    periodos: InMemoryPeriodRepository,
) -> GetCourseOfferingsUseCase:
    return GetCourseOfferingsUseCase(cursos, grupos, periodos)


@pytest.mark.unit
def test_get_course_offerings_when_course_does_not_exist_raises() -> None:
    caso = _caso_de_grupos(
        InMemoryCourseRepository(),
        InMemoryOfferingRepository(),
        InMemoryPeriodRepository([crear_periodo()]),
    )

    with pytest.raises(CourseNotFoundError):
        caso.execute(uuid4())


@pytest.mark.unit
def test_get_course_offerings_when_there_is_no_active_period_raises() -> None:
    materia = crear_materia()
    caso = _caso_de_grupos(
        InMemoryCourseRepository([materia]),
        InMemoryOfferingRepository(),
        InMemoryPeriodRepository([crear_periodo(is_active=False)]),
    )

    with pytest.raises(NoActivePeriodError):
        caso.execute(materia.id)


@pytest.mark.unit
def test_get_course_offerings_returns_only_groups_of_the_active_period() -> None:
    # El periodo NO llega por parametro: lo elige el caso de uso. Si lo eligiera el cliente,
    # se podria consultar —y en la Fase 3, inscribirse contra— semestres ya cerrados.
    materia = crear_materia()
    activo = crear_periodo(code="2025-2-V1")
    cerrado = crear_periodo(code="2025-1-V1", is_active=False)

    del_activo = crear_oferta(
        course_id=materia.id, enrollment_period_id=activo.id, group_number="01"
    )
    del_cerrado = crear_oferta(
        course_id=materia.id, enrollment_period_id=cerrado.id, group_number="02"
    )

    caso = _caso_de_grupos(
        InMemoryCourseRepository([materia]),
        InMemoryOfferingRepository([del_activo, del_cerrado]),
        InMemoryPeriodRepository([activo, cerrado]),
    )

    resultado = caso.execute(materia.id)

    assert [g.id for g in resultado.offerings] == [del_activo.id]
    assert resultado.period.code == "2025-2-V1"


@pytest.mark.unit
def test_get_course_offerings_when_course_is_not_offered_returns_empty_list_not_error() -> None:
    # Que una materia exista pero no se dicte este semestre es un resultado legitimo, no un
    # fallo: el estudiante tiene que poder ver que la materia existe y no esta disponible.
    materia = crear_materia()
    caso = _caso_de_grupos(
        InMemoryCourseRepository([materia]),
        InMemoryOfferingRepository(),
        InMemoryPeriodRepository([crear_periodo()]),
    )

    resultado = caso.execute(materia.id)

    assert resultado.offerings == []
    assert resultado.course.id == materia.id


# ---------------------------------------------------------------------------
# GetOfferingDetailUseCase
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_offering_detail_when_offering_does_not_exist_raises() -> None:
    caso = GetOfferingDetailUseCase(InMemoryOfferingRepository(), InMemoryCacheService(), TTL)

    with pytest.raises(OfferingNotFoundError):
        caso.execute(uuid4())


@pytest.mark.unit
def test_get_offering_detail_returns_the_offering() -> None:
    grupo = crear_oferta(total_capacity=40, enrolled_count=37)
    caso = GetOfferingDetailUseCase(
        InMemoryOfferingRepository([grupo]), InMemoryCacheService(), TTL
    )

    resultado = caso.execute(grupo.id)

    assert resultado.id == grupo.id
    assert resultado.available_slots() == 3


# ---------------------------------------------------------------------------
# GetCurrentPeriodUseCase
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_current_period_when_none_is_active_raises() -> None:
    caso = GetCurrentPeriodUseCase(InMemoryPeriodRepository(), clock=lambda: AHORA)

    with pytest.raises(NoActivePeriodError):
        caso.execute()


@pytest.mark.unit
def test_get_current_period_when_window_is_open_reports_it_open_with_countdown() -> None:
    periodo = crear_periodo(
        starts_at=AHORA - timedelta(hours=1), ends_at=AHORA + timedelta(hours=2)
    )
    caso = GetCurrentPeriodUseCase(InMemoryPeriodRepository([periodo]), clock=lambda: AHORA)

    resultado = caso.execute()

    assert resultado.is_open is True
    assert resultado.time_remaining_seconds == 7200


@pytest.mark.unit
def test_get_current_period_when_activated_but_not_started_reports_it_closed() -> None:
    # La distincion que el frontend necesita: hay periodo, pero todavia no abre. Permite
    # mostrar "la matricula abre el martes" en vez de "no hay periodo".
    periodo = crear_periodo(starts_at=AHORA + timedelta(days=2), ends_at=AHORA + timedelta(days=4))
    caso = GetCurrentPeriodUseCase(InMemoryPeriodRepository([periodo]), clock=lambda: AHORA)

    resultado = caso.execute()

    assert resultado.is_open is False
    assert resultado.period.code == periodo.code


@pytest.mark.unit
def test_get_current_period_when_window_already_closed_reports_zero_remaining() -> None:
    periodo = crear_periodo(starts_at=AHORA - timedelta(days=4), ends_at=AHORA - timedelta(days=2))
    caso = GetCurrentPeriodUseCase(InMemoryPeriodRepository([periodo]), clock=lambda: AHORA)

    resultado = caso.execute()

    assert resultado.is_open is False
    assert resultado.time_remaining_seconds == 0
