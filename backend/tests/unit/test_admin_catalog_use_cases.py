"""Pruebas de los casos de uso de catálogo y cupos de administración (iteración 4.3).

Cubren las tres operaciones de `API.md` sección 6 que tocan el catálogo: alta de materias,
apertura de grupos y ajuste de cupo. Lo que se comprueba aquí es la ORQUESTACIÓN —qué se
valida, en qué orden y si se confirma la transacción—; que las restricciones de PostgreSQL
sostengan lo mismo se verifica aparte, contra la base real.
"""

from __future__ import annotations

from datetime import time
from uuid import UUID, uuid4

import pytest

from app.application.use_cases.admin.adjust_offering_capacity import AdjustOfferingCapacityUseCase
from app.application.use_cases.admin.create_course import CreateCourseUseCase
from app.application.use_cases.admin.create_course_offering import CreateCourseOfferingUseCase
from app.application.use_cases.catalog import catalog_cache
from app.domain.entities.course_offering import CourseOffering
from app.domain.exceptions.admin import (
    CapacityBelowEnrolledError,
    ConcurrentOfferingUpdateError,
    DuplicateCourseCodeError,
    DuplicateOfferingGroupError,
    OverlappingScheduleError,
)
from app.domain.exceptions.catalog import (
    CourseNotFoundError,
    NoActivePeriodError,
    OfferingNotFoundError,
    ProfessorNotFoundError,
)
from app.domain.exceptions.invalid_value import InvalidCourseCodeError
from app.domain.value_objects.course_code import CourseCode
from tests.unit.doubles import (
    FakeUnitOfWork,
    InMemoryCacheService,
    InMemoryCourseRepository,
    InMemoryOfferingRepository,
    InMemoryPeriodRepository,
    InMemoryProfessorReader,
    InMemorySpaceRepository,
)
from tests.unit.factories import (
    crear_espacio,
    crear_franja_pedida,
    crear_materia,
    crear_oferta,
    crear_periodo,
)

#: El único espacio del inventario de estos tests. `crear_franja_pedida` pide «A-201» por
#: defecto, así que tiene que existir o toda alta de grupo fallaría con `SpaceNotFoundError`
#: por un motivo que no es el que se está probando.
_ESPACIO = crear_espacio(code="A-201")

# ---------------------------------------------------------------------------
# Alta de materias
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_crear_materia_la_persiste_y_confirma() -> None:
    materias = InMemoryCourseRepository()
    uow = FakeUnitOfWork()

    creada = CreateCourseUseCase(materias, uow).execute(code="fis201", name="Física II", credits=3)

    assert creada.code == CourseCode("FIS201")
    assert materias.find_by_code(CourseCode("FIS201")) is not None
    assert uow.confirmadas == 1


@pytest.mark.unit
def test_crear_materia_normaliza_el_codigo_antes_de_buscar_duplicados() -> None:
    """`mat101` y `MAT101` son la misma materia.

    Sin la normalización del value object, la comprobación de duplicados no encontraría nada y
    la restricción UNIQUE tampoco —son cadenas distintas—, así que el catálogo acabaría con
    dos materias que todo el mundo lee como una sola.
    """
    materias = InMemoryCourseRepository([crear_materia(code="MAT101")])

    with pytest.raises(DuplicateCourseCodeError):
        CreateCourseUseCase(materias, FakeUnitOfWork()).execute(
            code="  mat101 ", name="Cálculo I", credits=4
        )


@pytest.mark.unit
def test_crear_materia_con_codigo_invalido_no_abre_transaccion() -> None:
    uow = FakeUnitOfWork()

    with pytest.raises(InvalidCourseCodeError):
        CreateCourseUseCase(InMemoryCourseRepository(), uow).execute(
            code="101", name="Sin área", credits=4
        )

    assert uow.entradas == 0


@pytest.mark.unit
def test_crear_materia_duplicada_no_confirma() -> None:
    uow = FakeUnitOfWork()
    materias = InMemoryCourseRepository([crear_materia(code="MAT101")])

    with pytest.raises(DuplicateCourseCodeError):
        CreateCourseUseCase(materias, uow).execute(code="MAT101", name="Otra", credits=2)

    assert uow.confirmadas == 0


# ---------------------------------------------------------------------------
# Apertura de grupos
# ---------------------------------------------------------------------------


def _caso_de_grupos(
    *,
    con_periodo_activo: bool = True,
    materias: InMemoryCourseRepository | None = None,
    grupos: InMemoryOfferingRepository | None = None,
    docentes: InMemoryProfessorReader | None = None,
) -> tuple[CreateCourseOfferingUseCase, FakeUnitOfWork]:
    """Arma el caso de uso con dobles vacíos salvo lo que el test necesite declarar."""
    uow = FakeUnitOfWork()
    periodos = InMemoryPeriodRepository(
        [crear_periodo(is_active=True)] if con_periodo_activo else []
    )

    caso = CreateCourseOfferingUseCase(
        grupos or InMemoryOfferingRepository(),
        materias or InMemoryCourseRepository(),
        periodos,
        docentes or InMemoryProfessorReader(),
        InMemorySpaceRepository([_ESPACIO]),
        uow,
    )

    return caso, uow


@pytest.mark.unit
def test_crear_grupo_lo_abre_en_el_periodo_activo() -> None:
    """El período no viaja en la petición: se toma del activo."""
    materia = crear_materia()
    periodo = crear_periodo(is_active=True)
    periodos = InMemoryPeriodRepository([periodo, crear_periodo(code="2024-1-V1", is_active=False)])
    grupos = InMemoryOfferingRepository()
    uow = FakeUnitOfWork()

    creado = CreateCourseOfferingUseCase(
        grupos,
        InMemoryCourseRepository([materia]),
        periodos,
        InMemoryProfessorReader(),
        InMemorySpaceRepository([_ESPACIO]),
        uow,
    ).execute(
        course_id=materia.id,
        group_number="02",
        total_capacity=40,
        schedule=[crear_franja_pedida()],
    )

    assert creado.enrollment_period_id == periodo.id
    assert creado.enrolled_count == 0
    assert len(creado.schedule) == 1
    assert uow.confirmadas == 1


@pytest.mark.unit
def test_crear_grupo_sin_periodo_activo_falla() -> None:
    materia = crear_materia()
    caso, uow = _caso_de_grupos(
        con_periodo_activo=False, materias=InMemoryCourseRepository([materia])
    )

    with pytest.raises(NoActivePeriodError):
        caso.execute(course_id=materia.id, group_number="01", total_capacity=30, schedule=[])

    assert uow.confirmadas == 0


@pytest.mark.unit
def test_crear_grupo_de_materia_inexistente_falla() -> None:
    caso, _ = _caso_de_grupos()

    with pytest.raises(CourseNotFoundError):
        caso.execute(course_id=uuid4(), group_number="01", total_capacity=30, schedule=[])


@pytest.mark.unit
def test_crear_grupo_con_docente_inexistente_falla() -> None:
    """Sin esta comprobación, la clave foránea respondería 500 en vez de decir qué está mal."""
    materia = crear_materia()
    caso, _ = _caso_de_grupos(materias=InMemoryCourseRepository([materia]))

    with pytest.raises(ProfessorNotFoundError):
        caso.execute(
            course_id=materia.id,
            group_number="01",
            total_capacity=30,
            schedule=[],
            professor_id=uuid4(),
        )


@pytest.mark.unit
def test_crear_grupo_conserva_el_docente_asignado() -> None:
    materia = crear_materia()
    docente_id = uuid4()
    caso, _ = _caso_de_grupos(
        materias=InMemoryCourseRepository([materia]),
        docentes=InMemoryProfessorReader({docente_id}),
    )

    creado = caso.execute(
        course_id=materia.id,
        group_number="01",
        total_capacity=30,
        schedule=[],
        professor_id=docente_id,
    )

    assert creado.professor is not None
    assert creado.professor.id == docente_id


@pytest.mark.unit
def test_crear_grupo_repetido_en_el_mismo_periodo_falla() -> None:
    materia = crear_materia()
    periodo = crear_periodo(is_active=True)
    grupos = InMemoryOfferingRepository(
        [crear_oferta(course_id=materia.id, enrollment_period_id=periodo.id, group_number="01")]
    )
    uow = FakeUnitOfWork()

    caso = CreateCourseOfferingUseCase(
        grupos,
        InMemoryCourseRepository([materia]),
        InMemoryPeriodRepository([periodo]),
        InMemoryProfessorReader(),
        InMemorySpaceRepository([_ESPACIO]),
        uow,
    )

    with pytest.raises(DuplicateOfferingGroupError):
        caso.execute(course_id=materia.id, group_number="01", total_capacity=30, schedule=[])

    assert uow.confirmadas == 0


@pytest.mark.unit
def test_crear_grupo_con_franjas_que_se_cruzan_falla() -> None:
    """Un grupo no puede dictarse en dos sitios a la vez.

    El detector de choques de la inscripción compara grupos DISTINTOS, así que un grupo
    incoherente consigo mismo pasaría desapercibido y el estudiante acabaría con un horario
    imposible que nadie rechazó.
    """
    materia = crear_materia()
    caso, uow = _caso_de_grupos(materias=InMemoryCourseRepository([materia]))

    with pytest.raises(OverlappingScheduleError):
        caso.execute(
            course_id=materia.id,
            group_number="01",
            total_capacity=30,
            schedule=[
                crear_franja_pedida(day_of_week=2, start_time=time(8, 0), end_time=time(10, 0)),
                crear_franja_pedida(day_of_week=2, start_time=time(9, 0), end_time=time(11, 0)),
            ],
        )

    # Falla antes de abrir la transacción: la comprobación no depende de nada persistido.
    assert uow.entradas == 0


@pytest.mark.unit
def test_crear_grupo_admite_franjas_consecutivas() -> None:
    """Terminar a las 10:00 y empezar a las 10:00 no es un cruce, es una clase seguida."""
    materia = crear_materia()
    caso, _ = _caso_de_grupos(materias=InMemoryCourseRepository([materia]))

    creado = caso.execute(
        course_id=materia.id,
        group_number="01",
        total_capacity=30,
        schedule=[
            crear_franja_pedida(day_of_week=2, start_time=time(8, 0), end_time=time(10, 0)),
            crear_franja_pedida(day_of_week=2, start_time=time(10, 0), end_time=time(12, 0)),
        ],
    )

    assert len(creado.schedule) == 2


# ---------------------------------------------------------------------------
# Ajuste de cupo
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ampliar_el_cupo_lo_persiste_e_invalida_la_cache() -> None:
    """La entrada de caché guarda `total_capacity`: dejarla viva serviría cupos que no cuadran."""
    grupo = crear_oferta(total_capacity=40, enrolled_count=40)
    grupos = InMemoryOfferingRepository([grupo])
    cache = InMemoryCacheService()
    cache.envenenar(catalog_cache.clave_grupo(grupo.id), "{}")
    uow = FakeUnitOfWork()

    ajustado = AdjustOfferingCapacityUseCase(grupos, uow, cache).execute(
        grupo.id, total_capacity=50
    )

    assert ajustado.total_capacity == 50
    leido = grupos.find_by_id(grupo.id)
    assert leido is not None and leido.total_capacity == 50
    assert not cache.contiene(catalog_cache.clave_grupo(grupo.id))
    assert uow.confirmadas == 1


@pytest.mark.unit
def test_reducir_el_cupo_hasta_los_inscritos_esta_permitido() -> None:
    """Cerrar el grupo justo en su ocupación actual es válido: no expulsa a nadie."""
    grupo = crear_oferta(total_capacity=40, enrolled_count=25)
    grupos = InMemoryOfferingRepository([grupo])

    ajustado = AdjustOfferingCapacityUseCase(
        grupos, FakeUnitOfWork(), InMemoryCacheService()
    ).execute(grupo.id, total_capacity=25)

    assert ajustado.total_capacity == 25
    assert ajustado.available_slots() == 0


@pytest.mark.unit
def test_reducir_el_cupo_por_debajo_de_los_inscritos_falla() -> None:
    grupo = crear_oferta(total_capacity=40, enrolled_count=25)
    grupos = InMemoryOfferingRepository([grupo])
    uow = FakeUnitOfWork()

    with pytest.raises(CapacityBelowEnrolledError) as error:
        AdjustOfferingCapacityUseCase(grupos, uow, InMemoryCacheService()).execute(
            grupo.id, total_capacity=24
        )

    # El error dice cuántos hay inscritos: es el número que hace falta para elegir un cupo
    # válido sin tener que consultarlo aparte.
    assert error.value.details["enrolled_count"] == 25
    assert uow.confirmadas == 0


@pytest.mark.unit
def test_ajustar_el_cupo_de_un_grupo_inexistente_falla() -> None:
    with pytest.raises(OfferingNotFoundError):
        AdjustOfferingCapacityUseCase(
            InMemoryOfferingRepository(), FakeUnitOfWork(), InMemoryCacheService()
        ).execute(uuid4(), total_capacity=10)


class _GruposQueCambianUnaVez(InMemoryOfferingRepository):
    """Simula que otra operación se adelantó en el primer intento, y ya no en el segundo."""

    def __init__(self, offerings: list[CourseOffering]) -> None:
        super().__init__(offerings)
        self.intentos = 0

    def update_capacity(
        self, offering_id: UUID, *, new_capacity: int, expected_version: int
    ) -> bool:
        self.intentos += 1

        if self.intentos == 1:
            # Otra escritura movió la versión, así que este `UPDATE` no encuentra su fila.
            self.mover_version(offering_id)
            return False

        return super().update_capacity(
            offering_id, new_capacity=new_capacity, expected_version=expected_version
        )


class _GruposSiempreEnConflicto(InMemoryOfferingRepository):
    """Simula un grupo que cambia en cada intento, sin excepción."""

    def update_capacity(
        self, offering_id: UUID, *, new_capacity: int, expected_version: int
    ) -> bool:
        return False


@pytest.mark.unit
def test_ajustar_el_cupo_reintenta_cuando_pierde_la_carrera_una_vez() -> None:
    """El bloqueo optimista falla si otra escritura tocó el grupo; el reintento relee y aplica."""
    grupo = crear_oferta(total_capacity=40, enrolled_count=0, version=0)
    grupos = _GruposQueCambianUnaVez([grupo])

    ajustado = AdjustOfferingCapacityUseCase(
        grupos, FakeUnitOfWork(), InMemoryCacheService()
    ).execute(grupo.id, total_capacity=45)

    assert ajustado.total_capacity == 45
    assert grupos.intentos == 2


@pytest.mark.unit
def test_ajustar_el_cupo_se_rinde_tras_agotar_los_reintentos() -> None:
    """Rechazar es mejor que pisar en silencio la decisión de quien ganó la carrera."""
    grupo = crear_oferta(total_capacity=40)
    grupos = _GruposSiempreEnConflicto([grupo])
    uow = FakeUnitOfWork()

    with pytest.raises(ConcurrentOfferingUpdateError):
        AdjustOfferingCapacityUseCase(grupos, uow, InMemoryCacheService()).execute(
            grupo.id, total_capacity=45
        )

    assert uow.confirmadas == 0
