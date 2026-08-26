"""Pruebas unitarias de la cancelación y del horario del estudiante."""

from __future__ import annotations

from datetime import time
from uuid import uuid4

import pytest

from app.application.dtos.enrollment_dto import CancellationDTO
from app.application.use_cases.catalog import catalog_cache
from app.application.use_cases.enrollment.cancel_enrollment import CancelEnrollmentUseCase
from app.application.use_cases.enrollment.get_student_schedule import GetStudentScheduleUseCase
from app.domain.exceptions.catalog import NoActivePeriodError
from app.domain.exceptions.enrollment import (
    CorequisiteDependencyError,
    EnrollmentAlreadyCancelledError,
    EnrollmentNotFoundError,
)
from app.domain.value_objects.enrollment_status import EnrollmentStatus
from tests.unit.doubles import (
    FakeUnitOfWork,
    InMemoryCacheService,
    InMemoryCourseRepository,
    InMemoryEnrollmentRepository,
    InMemoryOfferingRepository,
    InMemoryPeriodRepository,
    InMemoryStudentRepository,
)
from tests.unit.factories import (
    AHORA,
    crear_espacio,
    crear_estudiante,
    crear_franja,
    crear_inscripcion,
    crear_materia,
    crear_oferta,
    crear_periodo,
    crear_profesor,
    crear_programa,
)

# ---------------------------------------------------------------------------
# CancelEnrollmentUseCase
# ---------------------------------------------------------------------------


class EscenarioCancelacion:
    """Monta la cancelación con un estudiante ya inscrito en un grupo."""

    def __init__(self, *, enrolled_count: int = 10, cancelada: bool = False) -> None:
        self.programa = crear_programa()
        self.estudiante = crear_estudiante(program_id=self.programa.id)
        self.estudiante_id = self.estudiante.id
        self.periodo = crear_periodo()
        self.materia = crear_materia(code="MAT101")
        self.grupo = crear_oferta(
            course_id=self.materia.id,
            enrollment_period_id=self.periodo.id,
            total_capacity=40,
            enrolled_count=enrolled_count,
        )
        self.inscripcion = crear_inscripcion(
            student_id=self.estudiante_id,
            course_offering_id=self.grupo.id,
            enrollment_period_id=self.periodo.id,
            status=EnrollmentStatus.CANCELLED if cancelada else EnrollmentStatus.ENROLLED,
        )

        self.inscripciones = InMemoryEnrollmentRepository([self.inscripcion])
        self.ofertas = InMemoryOfferingRepository([self.grupo])
        # Sin correquisitos declarados: la mayoría de estos tests van sobre el cupo y la
        # transacción, no sobre la regla del bloque, que tiene sus propios tests más abajo.
        self.materias = InMemoryCourseRepository([self.materia])
        self.estudiantes = InMemoryStudentRepository([self.estudiante])
        self.uow = FakeUnitOfWork()
        self.cache = InMemoryCacheService()

        self._montar()

    def _montar(self) -> None:
        """Reconstruye el caso de uso con las dependencias actuales del escenario."""
        self.caso = CancelEnrollmentUseCase(
            self.inscripciones,
            self.ofertas,
            self.materias,
            self.estudiantes,
            self.uow,
            self.cache,
            clock=lambda: AHORA,
        )

    def cancelar(self) -> CancellationDTO:
        return self.caso.execute(student_id=self.estudiante_id, enrollment_id=self.inscripcion.id)


@pytest.mark.unit
def test_cancel_marks_the_enrollment_as_cancelled() -> None:
    escenario = EscenarioCancelacion()

    escenario.cancelar()

    assert escenario.inscripcion.status is EnrollmentStatus.CANCELLED
    assert escenario.inscripcion.cancelled_at == AHORA


@pytest.mark.unit
def test_cancel_frees_the_seat() -> None:
    escenario = EscenarioCancelacion(enrolled_count=10)

    escenario.cancelar()

    assert escenario.grupo.enrolled_count == 9


@pytest.mark.unit
def test_cancel_commits_the_transaction() -> None:
    escenario = EscenarioCancelacion()

    escenario.cancelar()

    assert escenario.uow.confirmadas == 1


@pytest.mark.unit
def test_cancel_invalidates_the_offering_cache() -> None:
    escenario = EscenarioCancelacion()
    clave = catalog_cache.clave_grupo(escenario.grupo.id)
    escenario.cache.set(clave, "contenido-viejo", 30)

    escenario.cancelar()

    assert escenario.cache.get(clave) is None


@pytest.mark.unit
def test_cancel_an_enrollment_that_does_not_exist_raises() -> None:
    escenario = EscenarioCancelacion()

    with pytest.raises(EnrollmentNotFoundError):
        escenario.caso.execute(student_id=escenario.estudiante_id, enrollment_id=uuid4())


@pytest.mark.unit
def test_cancel_someone_elses_enrollment_answers_the_same_as_not_found() -> None:
    """Cancelar lo ajeno responde igual que si no existiera.

    Es deliberado: decir «esa inscripción no es tuya» confirmaría que ese identificador
    corresponde a una real, y permitiría enumerarlas probando identificadores hasta dar con
    una.
    """
    escenario = EscenarioCancelacion()

    with pytest.raises(EnrollmentNotFoundError):
        escenario.caso.execute(student_id=uuid4(), enrollment_id=escenario.inscripcion.id)


@pytest.mark.unit
def test_cancelling_someone_elses_enrollment_does_not_free_their_seat() -> None:
    escenario = EscenarioCancelacion(enrolled_count=10)

    with pytest.raises(EnrollmentNotFoundError):
        escenario.caso.execute(student_id=uuid4(), enrollment_id=escenario.inscripcion.id)

    assert escenario.grupo.enrolled_count == 10


@pytest.mark.unit
def test_cancelling_twice_raises() -> None:
    escenario = EscenarioCancelacion(cancelada=True)

    with pytest.raises(EnrollmentAlreadyCancelledError):
        escenario.cancelar()


@pytest.mark.unit
def test_cancelling_twice_does_not_free_the_seat_twice() -> None:
    """El cupo fantasma que dos personas podrían tomar.

    Si una cancelación se procesara dos veces, `enrolled_count` quedaría por debajo de la
    ocupación real. Hay dos defensas: la entidad rechaza cancelar lo ya cancelado, y
    `try_release_slot` nunca baja de cero.
    """
    escenario = EscenarioCancelacion(enrolled_count=10, cancelada=True)

    with pytest.raises(EnrollmentAlreadyCancelledError):
        escenario.cancelar()

    assert escenario.grupo.enrolled_count == 10


@pytest.mark.unit
def test_a_rejected_cancellation_does_not_commit() -> None:
    escenario = EscenarioCancelacion(cancelada=True)

    with pytest.raises(EnrollmentAlreadyCancelledError):
        escenario.cancelar()

    assert escenario.uow.confirmadas == 0


# ---------------------------------------------------------------------------
# Cancelación y correquisitos: el bloque se abandona entero, o no se abandona
# ---------------------------------------------------------------------------


class EscenarioDeBloque:
    """Monta un estudiante con dos materias inscritas y un correquisito entre ellas.

    `mutuo=True` declara la vuelta —`MAT101` exige también a `FIS101`—, que es lo que convierte
    la pareja en un bloque. El doble deduce la reciprocidad de las dos declaraciones, igual que
    el adaptador SQL la deduce del autojoin, así que estos tests ejercitan la regla y no una
    bandera puesta a mano.
    """

    def __init__(self, *, mutuo: bool) -> None:
        self.programa = crear_programa()
        self.estudiante = crear_estudiante(program_id=self.programa.id)
        self.periodo = crear_periodo()

        self.calculo = crear_materia(code="MAT101", name="Cálculo I")
        self.fisica = crear_materia(code="FIS101", name="Física I")

        self.grupo_calculo = crear_oferta(
            course_id=self.calculo.id,
            enrollment_period_id=self.periodo.id,
            group_number="01",
            enrolled_count=10,
        )
        self.grupo_fisica = crear_oferta(
            course_id=self.fisica.id,
            enrollment_period_id=self.periodo.id,
            group_number="02",
            enrolled_count=5,
        )

        self.inscripcion_calculo = crear_inscripcion(
            student_id=self.estudiante.id,
            course_offering_id=self.grupo_calculo.id,
            enrollment_period_id=self.periodo.id,
        )
        self.inscripcion_fisica = crear_inscripcion(
            student_id=self.estudiante.id,
            course_offering_id=self.grupo_fisica.id,
            enrollment_period_id=self.periodo.id,
        )

        correquisitos = {self.fisica.id: [self.calculo]}

        if mutuo:
            correquisitos[self.calculo.id] = [self.fisica]

        self.ofertas = InMemoryOfferingRepository([self.grupo_calculo, self.grupo_fisica])
        self.inscripciones = InMemoryEnrollmentRepository(
            [self.inscripcion_calculo, self.inscripcion_fisica]
        )
        self.cache = InMemoryCacheService()
        self.caso = CancelEnrollmentUseCase(
            self.inscripciones,
            self.ofertas,
            InMemoryCourseRepository(
                [self.calculo, self.fisica],
                corequisites=correquisitos,
                plan={self.programa.id: [(self.calculo.id, 1), (self.fisica.id, 1)]},
            ),
            InMemoryStudentRepository([self.estudiante]),
            FakeUnitOfWork(),
            self.cache,
            clock=lambda: AHORA,
        )

    def cancelar_calculo(self) -> CancellationDTO:
        """Cancela la materia EXIGIDA, que es la que puede dejar a la otra huérfana."""
        return self.caso.execute(
            student_id=self.estudiante.id, enrollment_id=self.inscripcion_calculo.id
        )


@pytest.mark.unit
def test_cancelling_a_course_another_enrolled_one_requires_is_rejected() -> None:
    """El agujero que esta iteración cierra.

    Hasta ahora cancelar no miraba los correquisitos, así que inscribir `FIS101` junto a
    `MAT101` —como exige la regla— y cancelar `MAT101` acto seguido dejaba al estudiante
    cursando Física sin el Cálculo que la acompaña: un estado que inscribir jamás habría
    aceptado.
    """
    escenario = EscenarioDeBloque(mutuo=False)

    with pytest.raises(CorequisiteDependencyError) as error:
        escenario.cancelar_calculo()

    assert error.value.details["required_by"] == ["FIS101"]


@pytest.mark.unit
def test_a_rejected_cancellation_does_not_free_any_seat() -> None:
    # El rechazo tiene que dejar el sistema exactamente como estaba: un cupo liberado por una
    # cancelación que no ocurrió es un cupo fantasma que dos personas podrían tomar.
    escenario = EscenarioDeBloque(mutuo=False)

    with pytest.raises(CorequisiteDependencyError):
        escenario.cancelar_calculo()

    assert escenario.grupo_calculo.enrolled_count == 10
    assert escenario.grupo_fisica.enrolled_count == 5


@pytest.mark.unit
def test_cancelling_one_of_a_mutual_block_cancels_the_whole_block() -> None:
    escenario = EscenarioDeBloque(mutuo=True)

    resultado = escenario.cancelar_calculo()

    assert {c.course_code for c in resultado.items} == {"MAT101", "FIS101"}
    assert resultado.arrastro_otras()
    assert escenario.inscripcion_calculo.status is EnrollmentStatus.CANCELLED
    assert escenario.inscripcion_fisica.status is EnrollmentStatus.CANCELLED


@pytest.mark.unit
def test_cancelling_a_mutual_block_frees_every_seat_of_the_block() -> None:
    escenario = EscenarioDeBloque(mutuo=True)

    escenario.cancelar_calculo()

    assert escenario.grupo_calculo.enrolled_count == 9
    assert escenario.grupo_fisica.enrolled_count == 4


@pytest.mark.unit
def test_cancelling_a_mutual_block_invalidates_the_cache_of_every_group() -> None:
    # Los cupos de las DOS acaban de cambiar. Invalidar solo el grupo pedido dejaría al
    # catálogo mostrando el otro lleno cuando ya tiene sitio.
    escenario = EscenarioDeBloque(mutuo=True)

    escenario.cancelar_calculo()

    assert escenario.cache.get(catalog_cache.clave_grupo(escenario.grupo_calculo.id)) is None
    assert escenario.cache.get(catalog_cache.clave_grupo(escenario.grupo_fisica.id)) is None


@pytest.mark.unit
def test_cancelling_the_dependent_side_first_is_always_allowed() -> None:
    """El orden correcto existe y la regla no lo estorba: primero la que depende.

    Es lo que hace que el rechazo sea una guía y no un callejón sin salida.
    """
    escenario = EscenarioDeBloque(mutuo=False)

    resultado = escenario.caso.execute(
        student_id=escenario.estudiante.id,
        enrollment_id=escenario.inscripcion_fisica.id,
    )

    assert [c.course_code for c in resultado.items] == ["FIS101"]
    assert not resultado.arrastro_otras()


# ---------------------------------------------------------------------------
# GetStudentScheduleUseCase
# ---------------------------------------------------------------------------


def _caso_horario(
    *,
    periodo_activo: bool = True,
    inscripciones: list | None = None,
    grupos: list | None = None,
    materias: list | None = None,
) -> tuple[GetStudentScheduleUseCase, object]:
    periodo = crear_periodo(is_active=periodo_activo, academic_period="2025-2")
    caso = GetStudentScheduleUseCase(
        InMemoryEnrollmentRepository(inscripciones or []),
        InMemoryOfferingRepository(grupos or []),
        InMemoryCourseRepository(materias or []),
        InMemoryPeriodRepository([periodo]),
    )
    return caso, periodo


@pytest.mark.unit
def test_schedule_when_nothing_is_enrolled_is_empty_not_an_error() -> None:
    # Un estudiante que aún no ha inscrito nada tiene un horario vacío, no un fallo.
    caso, _ = _caso_horario()

    horario = caso.execute(uuid4())

    assert horario.blocks == []
    assert horario.academic_period == "2025-2"


@pytest.mark.unit
def test_schedule_when_there_is_no_active_period_raises() -> None:
    caso, _ = _caso_horario(periodo_activo=False)

    with pytest.raises(NoActivePeriodError):
        caso.execute(uuid4())


@pytest.mark.unit
def test_schedule_includes_the_course_data_that_makes_it_readable() -> None:
    # «Lunes 8:00–10:00» no le sirve a nadie: hay que saber a qué clase ir, con quién y dónde.
    estudiante_id = uuid4()
    periodo = crear_periodo(academic_period="2025-2")
    materia = crear_materia(code="MAT101", name="Cálculo I")
    grupo = crear_oferta(
        course_id=materia.id,
        enrollment_period_id=periodo.id,
        group_number="01",
        professor=crear_profesor(full_name="Ana Pérez"),
        schedule=(
            crear_franja(
                day_of_week=1,
                start_time=time(8, 0),
                end_time=time(10, 0),
                space=crear_espacio(code="A-201"),
            ),
        ),
    )

    caso = GetStudentScheduleUseCase(
        InMemoryEnrollmentRepository(
            [
                crear_inscripcion(
                    student_id=estudiante_id,
                    course_offering_id=grupo.id,
                    enrollment_period_id=periodo.id,
                )
            ]
        ),
        InMemoryOfferingRepository([grupo]),
        InMemoryCourseRepository([materia]),
        InMemoryPeriodRepository([periodo]),
    )

    franja = caso.execute(estudiante_id).blocks[0]

    assert franja.course_code == "MAT101"
    assert franja.course_name == "Cálculo I"
    assert franja.group_number == "01"
    assert franja.professor == "Ana Pérez"
    assert franja.classroom == "A-201"
    assert (franja.day_of_week, franja.start_time, franja.end_time) == (
        1,
        time(8, 0),
        time(10, 0),
    )


@pytest.mark.unit
def test_schedule_comes_sorted_by_day_and_time() -> None:
    """Es como se lee un horario.

    El repositorio ya devuelve ordenadas las franjas de CADA grupo, pero aquí se mezclan las
    de varios: sin este orden, el horario saldría agrupado por materia en vez de por día.
    """
    estudiante_id = uuid4()
    periodo = crear_periodo(academic_period="2025-2")
    materia_a = crear_materia(code="AAA101", name="Primera")
    materia_b = crear_materia(code="BBB101", name="Segunda")

    # A se dicta el miércoles; B, el lunes y el jueves.
    grupo_a = crear_oferta(
        course_id=materia_a.id,
        enrollment_period_id=periodo.id,
        group_number="01",
        schedule=(crear_franja(day_of_week=3, start_time=time(10, 0), end_time=time(12, 0)),),
    )
    grupo_b = crear_oferta(
        course_id=materia_b.id,
        enrollment_period_id=periodo.id,
        group_number="02",
        schedule=(
            crear_franja(day_of_week=1, start_time=time(8, 0), end_time=time(10, 0)),
            crear_franja(day_of_week=4, start_time=time(14, 0), end_time=time(16, 0)),
        ),
    )

    caso = GetStudentScheduleUseCase(
        InMemoryEnrollmentRepository(
            [
                crear_inscripcion(
                    student_id=estudiante_id,
                    course_offering_id=g.id,
                    enrollment_period_id=periodo.id,
                )
                for g in (grupo_a, grupo_b)
            ]
        ),
        InMemoryOfferingRepository([grupo_a, grupo_b]),
        InMemoryCourseRepository([materia_a, materia_b]),
        InMemoryPeriodRepository([periodo]),
    )

    horario = caso.execute(estudiante_id)

    assert [(b.day_of_week, b.course_code) for b in horario.blocks] == [
        (1, "BBB101"),
        (3, "AAA101"),
        (4, "BBB101"),
    ]


@pytest.mark.unit
def test_a_cancelled_enrollment_does_not_appear_in_the_schedule() -> None:
    estudiante_id = uuid4()
    periodo = crear_periodo(academic_period="2025-2")
    materia = crear_materia(code="MAT101")
    grupo = crear_oferta(
        course_id=materia.id,
        enrollment_period_id=periodo.id,
        schedule=(crear_franja(),),
    )

    caso = GetStudentScheduleUseCase(
        InMemoryEnrollmentRepository(
            [
                crear_inscripcion(
                    student_id=estudiante_id,
                    course_offering_id=grupo.id,
                    enrollment_period_id=periodo.id,
                    status=EnrollmentStatus.CANCELLED,
                )
            ]
        ),
        InMemoryOfferingRepository([grupo]),
        InMemoryCourseRepository([materia]),
        InMemoryPeriodRepository([periodo]),
    )

    assert caso.execute(estudiante_id).blocks == []


@pytest.mark.unit
def test_the_schedule_of_another_student_is_not_returned() -> None:
    estudiante_id = uuid4()
    periodo = crear_periodo(academic_period="2025-2")
    materia = crear_materia(code="MAT101")
    grupo = crear_oferta(
        course_id=materia.id, enrollment_period_id=periodo.id, schedule=(crear_franja(),)
    )

    caso = GetStudentScheduleUseCase(
        InMemoryEnrollmentRepository(
            [
                crear_inscripcion(
                    student_id=uuid4(),
                    course_offering_id=grupo.id,
                    enrollment_period_id=periodo.id,
                )
            ]
        ),
        InMemoryOfferingRepository([grupo]),
        InMemoryCourseRepository([materia]),
        InMemoryPeriodRepository([periodo]),
    )

    assert caso.execute(estudiante_id).blocks == []
