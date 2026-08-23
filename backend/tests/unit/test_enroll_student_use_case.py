"""Pruebas unitarias de `EnrollStudentUseCase`.

Comprueban la ORQUESTACIÓN contra dobles en memoria: qué se valida, en qué orden, qué se
rechaza y si la transacción se confirma. Corren en milisegundos y sin infraestructura.

Lo que **no** cubren es la concurrencia, y conviene tenerlo claro: en memoria no hay dos hilos
compitiendo por una fila, así que un doble puede reproducir el comportamiento observable pero
no la atomicidad. Eso se verifica con hilos reales contra PostgreSQL en
`tests/integration/test_enrollment_concurrency.py`, que es donde vive la garantía de verdad.
"""

from __future__ import annotations

from datetime import time
from uuid import uuid4

import pytest

from app.application.use_cases.catalog import catalog_cache
from app.application.use_cases.enrollment.enroll_student import EnrollStudentUseCase
from app.domain.exceptions.catalog import OfferingNotFoundError
from app.domain.exceptions.enrollment import (
    AlreadyEnrolledError,
    CapacityExceededError,
    CourseNotInProgramError,
    EnrollmentPeriodInactiveError,
    PrerequisitesNotMetError,
    ScheduleConflictError,
)
from app.domain.value_objects.enrollment_status import EnrollmentStatus
from tests.unit.doubles import (
    FakeUnitOfWork,
    InMemoryAcademicHistory,
    InMemoryCacheService,
    InMemoryCourseRepository,
    InMemoryEnrollmentRepository,
    InMemoryOfferingRepository,
    InMemoryPeriodRepository,
    InMemoryStudentRepository,
)
from tests.unit.factories import (
    crear_estudiante,
    crear_franja,
    crear_inscripcion,
    crear_materia,
    crear_oferta,
    crear_periodo,
    crear_programa,
)


class Escenario:
    """Monta el caso de uso con todos sus dobles y deja a mano las piezas del test."""

    def __init__(
        self,
        *,
        total_capacity: int = 40,
        enrolled_count: int = 0,
        periodo_activo: bool = True,
        inscripciones: list | None = None,
        grupo_de_otro_periodo: bool = False,
        aprobadas: set | None = None,
        prerrequisitos: dict | None = None,
        en_el_plan: bool = True,
    ) -> None:
        self.periodo = crear_periodo(is_active=periodo_activo)
        self.materia = crear_materia(code="MAT101", name="Cálculo I")
        self.grupo = crear_oferta(
            course_id=self.materia.id,
            enrollment_period_id=uuid4() if grupo_de_otro_periodo else self.periodo.id,
            group_number="01",
            total_capacity=total_capacity,
            enrolled_count=enrolled_count,
        )
        self.programa = crear_programa()
        self.estudiante = crear_estudiante(program_id=self.programa.id)
        self.estudiante_id = self.estudiante.id

        self.inscripciones = InMemoryEnrollmentRepository(inscripciones or [])
        self.ofertas = InMemoryOfferingRepository([self.grupo])
        self.periodos = InMemoryPeriodRepository([self.periodo])
        # El plan de estudios se declara solo cuando el test va sobre esa regla: sin plan, el
        # doble acepta cualquier materia y el bloque de preparacion no se llena de ruido.
        plan = {self.programa.id: [(self.materia.id, 1)]} if en_el_plan else {uuid4(): []}
        self.materias = InMemoryCourseRepository(
            [self.materia], prerequisites=prerrequisitos or {}, plan=plan
        )
        self.estudiantes = InMemoryStudentRepository([self.estudiante])
        self.historial = InMemoryAcademicHistory({self.estudiante_id: aprobadas or set()})
        self.uow = FakeUnitOfWork()
        self.cache = InMemoryCacheService()

        self._montar()

    def _montar(self) -> None:
        """Reconstruye el caso de uso con las dependencias actuales del escenario."""
        self.caso = EnrollStudentUseCase(
            self.inscripciones,
            self.ofertas,
            self.periodos,
            self.materias,
            self.estudiantes,
            self.historial,
            self.uow,
            self.cache,
        )

    def con_inscripciones(self, *inscripciones) -> "Escenario":  # noqa: ANN002
        """Sustituye el repositorio de inscripciones y rehace el caso de uso."""
        self.inscripciones = InMemoryEnrollmentRepository(list(inscripciones))
        self._montar()
        return self

    def inscribir(self):  # noqa: ANN201
        return self.caso.execute(student_id=self.estudiante_id, course_offering_id=self.grupo.id)


# ---------------------------------------------------------------------------
# Camino feliz
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_enroll_when_everything_is_fine_returns_the_enrollment() -> None:
    escenario = Escenario(enrolled_count=10)

    resultado = escenario.inscribir()

    assert resultado.status is EnrollmentStatus.ENROLLED
    assert resultado.student_id == escenario.estudiante_id
    assert resultado.course_offering_id == escenario.grupo.id


@pytest.mark.unit
def test_enroll_response_carries_the_course_data_not_just_identifiers() -> None:
    # `API.md` incluye código, nombre y grupo en la respuesta: el estudiante acaba de
    # inscribirse y necesita leer «MAT101 — Cálculo I, grupo 01», no tres UUID.
    escenario = Escenario()

    resultado = escenario.inscribir()

    assert (resultado.course_code, resultado.course_name, resultado.group_number) == (
        "MAT101",
        "Cálculo I",
        "01",
    )


@pytest.mark.unit
def test_enroll_takes_one_seat_from_the_group() -> None:
    escenario = Escenario(total_capacity=40, enrolled_count=10)

    escenario.inscribir()

    assert escenario.grupo.enrolled_count == 11


@pytest.mark.unit
def test_enroll_commits_the_transaction() -> None:
    # Un caso de uso que se olvidara del `commit` perdería todas las escrituras en producción
    # y aun así pasaría cualquier test que solo mirase el valor devuelto.
    escenario = Escenario()

    escenario.inscribir()

    assert escenario.uow.confirmadas == 1


@pytest.mark.unit
def test_enroll_persists_the_enrollment() -> None:
    escenario = Escenario()

    resultado = escenario.inscribir()

    assert escenario.inscripciones.guardados == [resultado.id]


@pytest.mark.unit
def test_enroll_invalidates_the_offering_cache() -> None:
    # `BEST_PRACTICES.md` sección 9: al inscribir se invalida la caché del grupo afectado.
    escenario = Escenario()
    clave = catalog_cache.clave_grupo(escenario.grupo.id)
    escenario.cache.set(clave, "contenido-viejo", 30)

    escenario.inscribir()

    assert escenario.cache.get(clave) is None


@pytest.mark.unit
def test_enroll_on_the_last_seat_succeeds() -> None:
    escenario = Escenario(total_capacity=40, enrolled_count=39)

    escenario.inscribir()

    assert escenario.grupo.enrolled_count == 40


# ---------------------------------------------------------------------------
# Rechazos
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_enroll_when_group_is_full_raises_capacity_exceeded() -> None:
    escenario = Escenario(total_capacity=40, enrolled_count=40)

    with pytest.raises(CapacityExceededError):
        escenario.inscribir()


@pytest.mark.unit
def test_enroll_when_group_is_full_does_not_commit() -> None:
    escenario = Escenario(total_capacity=40, enrolled_count=40)

    with pytest.raises(CapacityExceededError):
        escenario.inscribir()

    assert escenario.uow.confirmadas == 0


@pytest.mark.unit
def test_enroll_when_there_is_no_active_period_raises() -> None:
    escenario = Escenario(periodo_activo=False)

    with pytest.raises(EnrollmentPeriodInactiveError):
        escenario.inscribir()


@pytest.mark.unit
def test_enroll_when_no_active_period_never_opens_a_transaction() -> None:
    # La comprobación ocurre antes de abrir la transacción: resolverlo fuera acorta el tiempo
    # que la transacción crítica mantiene la fila tomada.
    escenario = Escenario(periodo_activo=False)

    with pytest.raises(EnrollmentPeriodInactiveError):
        escenario.inscribir()

    assert escenario.uow.entradas == 0


@pytest.mark.unit
def test_enroll_in_a_group_from_a_closed_period_is_rejected() -> None:
    # El grupo existe, pero pertenece a un semestre que ya cerró. Se rechaza como período
    # inactivo y no como grupo inexistente: lo que no está abierto es su ventana.
    escenario = Escenario(grupo_de_otro_periodo=True)

    with pytest.raises(EnrollmentPeriodInactiveError):
        escenario.inscribir()


@pytest.mark.unit
def test_enroll_when_offering_does_not_exist_raises() -> None:
    escenario = Escenario()

    with pytest.raises(OfferingNotFoundError):
        escenario.caso.execute(student_id=escenario.estudiante_id, course_offering_id=uuid4())


@pytest.mark.unit
def test_enroll_when_already_enrolled_raises() -> None:
    escenario = Escenario()
    ya_inscrito = crear_inscripcion(
        student_id=escenario.estudiante_id,
        course_offering_id=escenario.grupo.id,
        enrollment_period_id=escenario.periodo.id,
    )
    escenario.con_inscripciones(ya_inscrito)

    with pytest.raises(AlreadyEnrolledError):
        escenario.inscribir()


@pytest.mark.unit
def test_enroll_when_already_enrolled_does_not_take_another_seat() -> None:
    # Sin esta guarda, la misma persona descontaría dos cupos del grupo.
    escenario = Escenario(enrolled_count=10)
    ya_inscrito = crear_inscripcion(
        student_id=escenario.estudiante_id,
        course_offering_id=escenario.grupo.id,
        enrollment_period_id=escenario.periodo.id,
    )
    escenario.con_inscripciones(ya_inscrito)

    with pytest.raises(AlreadyEnrolledError):
        escenario.inscribir()

    assert escenario.grupo.enrolled_count == 10


# ---------------------------------------------------------------------------
# Reinscripción tras cancelar
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_enroll_after_cancelling_reactivates_the_existing_row() -> None:
    """Reinscribirse en un grupo cancelado reactiva la fila, no crea otra.

    La restricción `UNIQUE (student_id, course_offering_id, enrollment_period_id)` impide
    insertar una segunda. Reactivar preserva además el rastro de que hubo una cancelación, que
    borrar la fila destruiría.
    """
    escenario = Escenario(enrolled_count=10)
    cancelada = crear_inscripcion(
        student_id=escenario.estudiante_id,
        course_offering_id=escenario.grupo.id,
        enrollment_period_id=escenario.periodo.id,
        status=EnrollmentStatus.CANCELLED,
    )
    escenario.con_inscripciones(cancelada)

    resultado = escenario.inscribir()

    assert resultado.id == cancelada.id
    assert cancelada.is_active() is True
    assert cancelada.cancelled_at is None


@pytest.mark.unit
def test_reenrolling_after_cancelling_takes_a_seat_again() -> None:
    escenario = Escenario(enrolled_count=10)
    cancelada = crear_inscripcion(
        student_id=escenario.estudiante_id,
        course_offering_id=escenario.grupo.id,
        enrollment_period_id=escenario.periodo.id,
        status=EnrollmentStatus.CANCELLED,
    )
    escenario.con_inscripciones(cancelada)

    escenario.inscribir()

    assert escenario.grupo.enrolled_count == 11


# ---------------------------------------------------------------------------
# Reglas academicas: que esten CABLEADAS al flujo
# ---------------------------------------------------------------------------
#
# Que cada regla decida bien se prueba en `test_domain_services.py`, sobre los servicios
# aislados. Lo que se comprueba aqui es otra cosa: que el caso de uso las invoca, en el momento
# correcto y sin dejar efectos a medias. Una regla perfecta que nadie llama no protege nada.


@pytest.mark.unit
def test_enroll_a_course_outside_the_students_curriculum_is_rejected() -> None:
    # Un estudiante de Derecho no debe poder inscribir Programacion II, aunque la materia
    # exista y tenga cupo. `API.md` lo tipifica como 403 y no como 409: no es un conflicto de
    # estado, es una operacion que a esta persona no le corresponde.
    escenario = Escenario(en_el_plan=False)

    with pytest.raises(CourseNotInProgramError):
        escenario.inscribir()


@pytest.mark.unit
def test_enroll_without_the_required_prerequisite_is_rejected() -> None:
    escenario = Escenario()
    calculo_i = crear_materia(code="MAT101")
    escenario.materias = InMemoryCourseRepository(
        [escenario.materia, calculo_i],
        prerequisites={escenario.materia.id: [calculo_i]},
        plan={escenario.programa.id: [(escenario.materia.id, 1)]},
    )
    escenario._montar()

    with pytest.raises(PrerequisitesNotMetError) as error:
        escenario.inscribir()

    assert error.value.details["missing_prerequisites"] == ["MAT101"]


@pytest.mark.unit
def test_enroll_with_the_prerequisite_approved_succeeds() -> None:
    calculo_i = crear_materia(code="MAT101")
    escenario = Escenario(aprobadas={calculo_i.id})
    escenario.materias = InMemoryCourseRepository(
        [escenario.materia, calculo_i],
        prerequisites={escenario.materia.id: [calculo_i]},
        plan={escenario.programa.id: [(escenario.materia.id, 1)]},
    )
    escenario._montar()

    assert escenario.inscribir().status is EnrollmentStatus.ENROLLED


@pytest.mark.unit
def test_enroll_in_a_group_that_clashes_with_an_active_enrollment_is_rejected() -> None:
    escenario = Escenario()
    ya_inscrito = crear_oferta(
        enrollment_period_id=escenario.periodo.id,
        group_number="02",
        schedule=(crear_franja(day_of_week=1, start_time=time(8, 0), end_time=time(10, 0)),),
    )
    escenario.grupo.schedule = (
        crear_franja(day_of_week=1, start_time=time(9, 0), end_time=time(11, 0)),
    )
    escenario.ofertas = InMemoryOfferingRepository([escenario.grupo, ya_inscrito])
    escenario.inscripciones = InMemoryEnrollmentRepository(
        [
            crear_inscripcion(
                student_id=escenario.estudiante_id,
                course_offering_id=ya_inscrito.id,
                enrollment_period_id=escenario.periodo.id,
            )
        ]
    )
    escenario._montar()

    with pytest.raises(ScheduleConflictError) as error:
        escenario.inscribir()

    assert error.value.details["conflicting_offering_id"] == str(ya_inscrito.id)


@pytest.mark.unit
def test_a_cancelled_enrollment_does_not_block_the_schedule() -> None:
    # Una inscripcion cancelada no ocupa horario. Contarla impediria reorganizar la matricula:
    # cancelar un grupo y tomar otro a la misma hora es justamente lo que se espera poder hacer.
    escenario = Escenario()
    cancelado = crear_oferta(
        enrollment_period_id=escenario.periodo.id,
        group_number="02",
        schedule=(crear_franja(day_of_week=1, start_time=time(8, 0), end_time=time(10, 0)),),
    )
    escenario.grupo.schedule = (
        crear_franja(day_of_week=1, start_time=time(9, 0), end_time=time(11, 0)),
    )
    escenario.ofertas = InMemoryOfferingRepository([escenario.grupo, cancelado])
    escenario.inscripciones = InMemoryEnrollmentRepository(
        [
            crear_inscripcion(
                student_id=escenario.estudiante_id,
                course_offering_id=cancelado.id,
                enrollment_period_id=escenario.periodo.id,
                status=EnrollmentStatus.CANCELLED,
            )
        ]
    )
    escenario._montar()

    assert escenario.inscribir().status is EnrollmentStatus.ENROLLED


@pytest.mark.unit
def test_academic_rules_are_checked_before_touching_the_seat_count() -> None:
    """El orden importa: primero las reglas, despues el cupo.

    Descontar y revertir por una validacion fallida seria trabajo desperdiciado en la operacion
    mas disputada del sistema, y durante ese instante el cupo apareceria ocupado ante cualquier
    otra peticion.
    """
    escenario = Escenario(enrolled_count=10, en_el_plan=False)

    with pytest.raises(CourseNotInProgramError):
        escenario.inscribir()

    assert escenario.grupo.enrolled_count == 10
    assert escenario.uow.confirmadas == 0


@pytest.mark.unit
def test_a_rejected_enrollment_leaves_no_row_behind() -> None:
    escenario = Escenario(en_el_plan=False)

    with pytest.raises(CourseNotInProgramError):
        escenario.inscribir()

    assert escenario.inscripciones.guardados == []
