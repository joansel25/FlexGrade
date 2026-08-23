"""Pruebas unitarias de la política de caché del catálogo.

El test más importante de todo el archivo es
`test_offering_detail_always_reads_the_live_enrolled_count`: comprueba que el cupo ocupado
se relee de la base de datos incluso cuando el grupo viene de la caché. Es la regla que
sostiene el requisito no funcional del sistema, y la que se rompería si alguien «optimiza»
devolviendo la entrada cacheada tal cual.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.application.use_cases.catalog import catalog_cache
from app.application.use_cases.catalog.get_course_detail import GetCourseDetailUseCase
from app.application.use_cases.catalog.get_offering_detail import GetOfferingDetailUseCase
from app.application.use_cases.catalog.list_courses import ListCoursesUseCase
from app.domain.exceptions.catalog import CourseNotFoundError, OfferingNotFoundError
from tests.unit.doubles import (
    CacheCaida,
    ContadorDeConsultas,
    InMemoryCacheService,
    InMemoryCourseRepository,
    InMemoryOfferingRepository,
)
from tests.unit.factories import crear_materia, crear_oferta

TTL = 30

# ---------------------------------------------------------------------------
# La regla crítica: el cupo nunca se sirve desde la caché
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_offering_detail_always_reads_the_live_enrolled_count() -> None:
    """El cupo ocupado se relee de la base de datos aunque el grupo venga de la caché.

    Escenario: un estudiante consulta un grupo con 3 cupos libres; otros dos se inscriben; el
    mismo estudiante recarga dentro de la ventana del TTL. Debe ver 1 cupo, no 3. Servir el
    valor cacheado le haría creer que tiene plaza y llevarle a un 409 al inscribirse.
    """
    grupo = crear_oferta(total_capacity=40, enrolled_count=37)
    repo = ContadorDeConsultas(InMemoryOfferingRepository([grupo]))
    cache = InMemoryCacheService()
    caso = GetOfferingDetailUseCase(repo, cache, TTL)

    primera = caso.execute(grupo.id)
    assert primera.available_slots() == 3

    # Dos inscripciones más, directamente sobre el dato que ve el repositorio.
    grupo.enrolled_count = 39

    segunda = caso.execute(grupo.id)

    assert segunda.available_slots() == 1, "el cupo se sirvió desde la caché"
    # La parte estática sí vino de la caché: no se volvió a cargar el grupo entero.
    assert repo.llamadas_find_by_id == 1
    # Pero el contador se leyó en las dos peticiones, sin excepción.
    assert repo.llamadas_count_enrolled == 2


@pytest.mark.unit
def test_offering_detail_reads_the_live_count_even_on_a_cache_miss() -> None:
    # En el camino sin caché el valor ya viene correcto y la lectura es redundante. Se hace
    # igualmente: tener un solo camino posible es lo que garantiza que no exista ninguna ruta
    # por la que se sirva un cupo con antigüedad.
    grupo = crear_oferta()
    repo = ContadorDeConsultas(InMemoryOfferingRepository([grupo]))

    GetOfferingDetailUseCase(repo, InMemoryCacheService(), TTL).execute(grupo.id)

    assert repo.llamadas_count_enrolled == 1


@pytest.mark.unit
def test_offering_detail_caches_professor_and_schedule() -> None:
    from tests.unit.factories import crear_franja, crear_profesor

    grupo = crear_oferta(professor=crear_profesor(), schedule=(crear_franja(),))
    cache = InMemoryCacheService()
    caso = GetOfferingDetailUseCase(InMemoryOfferingRepository([grupo]), cache, TTL)

    caso.execute(grupo.id)
    desde_cache = caso.execute(grupo.id)

    assert desde_cache.professor is not None
    assert desde_cache.professor.full_name == "Ana Pérez"
    assert len(desde_cache.schedule) == 1
    assert desde_cache.schedule[0].classroom == "A-201"


@pytest.mark.unit
def test_offering_detail_when_group_was_deleted_while_cached_raises_and_invalidates() -> None:
    # El grupo se cachea y luego desaparece de la base. `count_enrolled` devuelve `None` y esa
    # es la señal: se responde 404 y se limpia la entrada para no repetir el camino inútil.
    grupo = crear_oferta()
    repo_interno = InMemoryOfferingRepository([grupo])
    cache = InMemoryCacheService()
    caso = GetOfferingDetailUseCase(repo_interno, cache, TTL)

    caso.execute(grupo.id)
    assert cache.contiene(catalog_cache.clave_grupo(grupo.id))

    vacio = GetOfferingDetailUseCase(InMemoryOfferingRepository(), cache, TTL)

    with pytest.raises(OfferingNotFoundError):
        vacio.execute(grupo.id)

    assert not cache.contiene(catalog_cache.clave_grupo(grupo.id))


@pytest.mark.unit
def test_offering_detail_when_missing_does_not_cache_anything() -> None:
    cache = InMemoryCacheService()
    caso = GetOfferingDetailUseCase(InMemoryOfferingRepository(), cache, TTL)

    with pytest.raises(OfferingNotFoundError):
        caso.execute(uuid4())

    assert cache.escrituras == 0


# ---------------------------------------------------------------------------
# Listado de materias
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_list_courses_second_call_is_served_from_cache() -> None:
    cache = InMemoryCacheService()
    caso = ListCoursesUseCase(InMemoryCourseRepository([crear_materia()]), cache, TTL)

    primera = caso.execute()
    segunda = caso.execute()

    assert [c.id for c in primera.items] == [c.id for c in segunda.items]
    assert primera.total == segunda.total
    # Una sola escritura: la segunda llamada encontró la entrada y no volvió a guardarla.
    assert cache.escrituras == 1


@pytest.mark.unit
def test_list_courses_different_filters_do_not_share_a_cache_entry() -> None:
    # Compartir entrada entre búsquedas distintas es la forma más silenciosa de servir datos
    # equivocados: el estudiante buscaría "Física" y vería el resultado de "Cálculo".
    calculo = crear_materia(code="MAT101", name="Cálculo I")
    fisica = crear_materia(code="FIS101", name="Física")
    caso = ListCoursesUseCase(
        InMemoryCourseRepository([calculo, fisica]), InMemoryCacheService(), TTL
    )

    assert [c.id for c in caso.execute(search="Cálculo").items] == [calculo.id]
    assert [c.id for c in caso.execute(search="Física").items] == [fisica.id]


@pytest.mark.unit
def test_list_courses_pages_do_not_share_a_cache_entry() -> None:
    materias = [crear_materia(code=f"MAT{i:03d}") for i in range(1, 6)]
    caso = ListCoursesUseCase(InMemoryCourseRepository(materias), InMemoryCacheService(), TTL)

    primera = caso.execute(page=1, size=2)
    segunda = caso.execute(page=2, size=2)

    assert {c.id for c in primera.items}.isdisjoint({c.id for c in segunda.items})


@pytest.mark.unit
def test_list_courses_normalizes_the_key_so_equivalent_searches_share_an_entry() -> None:
    # `"Cálculo"` y `" cálculo "` producen el mismo resultado; ocupar dos entradas distintas
    # con contenido idéntico sería desperdiciar memoria durante el pico.
    cache = InMemoryCacheService()
    caso = ListCoursesUseCase(InMemoryCourseRepository([crear_materia()]), cache, TTL)

    caso.execute(search="Cálculo")
    caso.execute(search="  cálculo  ")

    assert cache.escrituras == 1


@pytest.mark.unit
@pytest.mark.parametrize("pagina", [0, -3])
def test_list_courses_sanitizes_the_page_before_building_the_key(pagina: int) -> None:
    # El saneado ocurre ANTES de construir la clave. Si no, `?page=0` y `?page=-3` serían dos
    # entradas distintas con exactamente el mismo contenido que `?page=1`.
    cache = InMemoryCacheService()
    caso = ListCoursesUseCase(InMemoryCourseRepository([crear_materia()]), cache, TTL)

    caso.execute(page=1, size=20)
    caso.execute(page=pagina, size=20)

    assert cache.escrituras == 1


# ---------------------------------------------------------------------------
# Detalle de materia
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_course_detail_second_call_is_served_from_cache() -> None:
    materia = crear_materia()
    cache = InMemoryCacheService()
    caso = GetCourseDetailUseCase(InMemoryCourseRepository([materia]), cache, TTL)

    caso.execute(materia.id)
    segunda = caso.execute(materia.id)

    assert segunda.course.id == materia.id
    assert cache.escrituras == 1


@pytest.mark.unit
def test_course_detail_when_missing_does_not_cache_anything() -> None:
    cache = InMemoryCacheService()
    caso = GetCourseDetailUseCase(InMemoryCourseRepository(), cache, TTL)

    with pytest.raises(CourseNotFoundError):
        caso.execute(uuid4())

    assert cache.escrituras == 0


# ---------------------------------------------------------------------------
# Resiliencia: la caché nunca puede tumbar una petición
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_list_courses_still_works_when_the_cache_is_down() -> None:
    materia = crear_materia()

    resultado = ListCoursesUseCase(InMemoryCourseRepository([materia]), CacheCaida(), TTL).execute()

    assert [c.id for c in resultado.items] == [materia.id]


@pytest.mark.unit
def test_offering_detail_still_works_when_the_cache_is_down() -> None:
    grupo = crear_oferta(total_capacity=40, enrolled_count=10)

    resultado = GetOfferingDetailUseCase(
        InMemoryOfferingRepository([grupo]), CacheCaida(), TTL
    ).execute(grupo.id)

    assert resultado.available_slots() == 30


@pytest.mark.unit
@pytest.mark.parametrize(
    "basura", ["no es json", "[]", "null", '{"items": "no es una lista"}', '{"total": 1}']
)
def test_list_courses_ignores_a_corrupt_cache_entry(basura: str) -> None:
    # Una entrada ilegible se trata como si no existiera. Puede pasar si alguien escribe a
    # mano en Redis o si una versión anterior dejó otro formato. La petición debe responder
    # igual, no reventar con un KeyError imposible de reproducir en local.
    materia = crear_materia()
    cache = InMemoryCacheService()
    caso = ListCoursesUseCase(InMemoryCourseRepository([materia]), cache, TTL)
    cache.envenenar(
        catalog_cache.clave_listado(page=1, size=20, program_id=None, semester=None, search=None),
        basura,
    )

    resultado = caso.execute()

    assert [c.id for c in resultado.items] == [materia.id]


@pytest.mark.unit
@pytest.mark.parametrize("basura", ["no es json", "{}", '{"id": "no-es-un-uuid"}', "[1, 2, 3]"])
def test_offering_detail_ignores_a_corrupt_cache_entry(basura: str) -> None:
    grupo = crear_oferta(total_capacity=40, enrolled_count=5)
    cache = InMemoryCacheService()
    caso = GetOfferingDetailUseCase(InMemoryOfferingRepository([grupo]), cache, TTL)
    cache.envenenar(catalog_cache.clave_grupo(grupo.id), basura)

    resultado = caso.execute(grupo.id)

    assert resultado.available_slots() == 35


# ---------------------------------------------------------------------------
# Serialización
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_offering_round_trip_preserves_every_field() -> None:
    from tests.unit.factories import crear_franja, crear_profesor

    original = crear_oferta(
        total_capacity=40,
        enrolled_count=37,
        version=7,
        professor=crear_profesor(),
        schedule=(crear_franja(day_of_week=1), crear_franja(day_of_week=3, classroom=None)),
    )

    recuperado = catalog_cache.grupo_desde_json(catalog_cache.grupo_a_json(original))

    assert recuperado == original


@pytest.mark.unit
def test_offering_round_trip_without_professor_or_schedule() -> None:
    original = crear_oferta(professor=None, schedule=())

    assert catalog_cache.grupo_desde_json(catalog_cache.grupo_a_json(original)) == original


@pytest.mark.unit
def test_course_round_trip_preserves_the_value_object() -> None:
    original = crear_materia(code="MAT101")

    recuperada = catalog_cache.materia_desde_json(catalog_cache.materia_a_json(original))

    assert recuperada == original
    assert recuperada is not None
    assert recuperada.code.value == "MAT101"


@pytest.mark.unit
def test_cache_keys_carry_a_version_prefix() -> None:
    # La versión en la clave es lo que permite invalidar todas las entradas de golpe cuando
    # cambie el formato. Sin ella, durante los segundos del TTL convivirían entradas viejas
    # con código que espera el formato nuevo.
    assert catalog_cache.clave_grupo(uuid4()).startswith("catalog:v1:")
    assert catalog_cache.clave_materia(uuid4()).startswith("catalog:v1:")
