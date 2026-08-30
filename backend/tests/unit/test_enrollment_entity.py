"""Pruebas unitarias de la entidad `Enrollment` y del descuento de cupo de `CourseOffering`.

Aquí vive la invariante que sostiene el requisito no funcional del sistema. Estos tests corren
en milisegundos y sin base de datos, precisamente porque la regla está dentro de la entidad y
no dispersa entre el caso de uso, el repositorio y el SQL.

Lo que estas pruebas **no** cubren es la concurrencia: `reserve_slot()` opera sobre una copia
en memoria y dos peticiones simultáneas pueden pasar su comprobación a la vez. Eso lo resuelven
el bloqueo optimista y el `CHECK` de PostgreSQL, y se verifica con hilos reales en la iteración
3.2.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

from app.domain.entities.enrollment import Enrollment
from app.domain.exceptions.enrollment import CapacityExceededError, EnrollmentAlreadyCancelledError
from app.domain.value_objects.enrollment_status import EnrollmentStatus
from tests.unit.factories import AHORA, crear_inscripcion, crear_oferta

# ---------------------------------------------------------------------------
# CourseOffering.reserve_slot — la invariante de cupo
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_reserve_slot_when_there_is_room_takes_one() -> None:
    grupo = crear_oferta(total_capacity=40, enrolled_count=10)

    grupo.reserve_slot()

    assert grupo.enrolled_count == 11
    assert grupo.available_slots() == 29


@pytest.mark.unit
def test_reserve_slot_on_the_last_seat_succeeds_and_fills_the_group() -> None:
    # El caso que define la fase: quien llega primero al último cupo se lo lleva.
    grupo = crear_oferta(total_capacity=40, enrolled_count=39)

    grupo.reserve_slot()

    assert grupo.enrolled_count == 40
    assert grupo.is_full()


@pytest.mark.unit
def test_reserve_slot_when_group_is_full_raises_capacity_exceeded() -> None:
    grupo = crear_oferta(total_capacity=40, enrolled_count=40)

    with pytest.raises(CapacityExceededError):
        grupo.reserve_slot()


@pytest.mark.unit
def test_reserve_slot_when_full_does_not_modify_the_count() -> None:
    # La excepción tiene que dejar la entidad como estaba. Un `enrolled_count` incrementado
    # antes de comprobar, aunque después se lanzara, produciría sobrecupo en cuanto alguien
    # capturase la excepción y persistiera el objeto igualmente.
    grupo = crear_oferta(total_capacity=40, enrolled_count=40)

    with pytest.raises(CapacityExceededError):
        grupo.reserve_slot()

    assert grupo.enrolled_count == 40


@pytest.mark.unit
def test_capacity_exceeded_carries_the_numbers_in_details() -> None:
    # `API.md` documenta que la respuesta 409 lleva capacidad y ocupación: el estudiante
    # necesita ver «40 de 40», no solo «no hay cupo».
    grupo = crear_oferta(total_capacity=40, enrolled_count=40)

    with pytest.raises(CapacityExceededError) as error:
        grupo.reserve_slot()

    assert error.value.details == {
        "offering_id": str(grupo.id),
        "capacity": 40,
        "enrolled": 40,
    }


@pytest.mark.unit
def test_reserve_slot_bumps_the_version_for_optimistic_locking() -> None:
    # El repositorio persistirá el par (enrolled_count, version) comparando contra la versión
    # que la entidad tenía al leerse. Sin este incremento, dos escrituras seguidas usarían la
    # misma versión esperada y la segunda sobrescribiría a la primera sin detectar el
    # conflicto.
    grupo = crear_oferta(version=5)

    grupo.reserve_slot()

    assert grupo.version == 6


@pytest.mark.unit
def test_can_accept_enrollment_reflects_the_remaining_room() -> None:
    assert crear_oferta(total_capacity=40, enrolled_count=39).can_accept_enrollment() is True
    assert crear_oferta(total_capacity=40, enrolled_count=40).can_accept_enrollment() is False


# ---------------------------------------------------------------------------
# CourseOffering.release_slot
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_release_slot_frees_one_seat() -> None:
    grupo = crear_oferta(total_capacity=40, enrolled_count=40)

    grupo.release_slot()

    assert grupo.enrolled_count == 39
    assert grupo.is_full() is False


@pytest.mark.unit
def test_release_slot_never_goes_below_zero() -> None:
    # Un contador negativo produciría cupos fantasma: `available_slots()` daría más plazas de
    # las que el grupo tiene, y dos personas podrían tomar la misma.
    grupo = crear_oferta(total_capacity=40, enrolled_count=0)

    grupo.release_slot()

    assert grupo.enrolled_count == 0


@pytest.mark.unit
def test_release_slot_bumps_the_version() -> None:
    grupo = crear_oferta(enrolled_count=5, version=3)

    grupo.release_slot()

    assert grupo.version == 4


@pytest.mark.unit
def test_reserve_and_release_return_the_group_to_its_original_count() -> None:
    grupo = crear_oferta(total_capacity=40, enrolled_count=20)

    grupo.reserve_slot()
    grupo.release_slot()

    assert grupo.enrolled_count == 20


# ---------------------------------------------------------------------------
# Enrollment
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_create_produces_an_active_enrollment() -> None:
    inscripcion = Enrollment.create(
        student_id=uuid4(),
        course_offering_id=uuid4(),
        course_id=uuid4(),
        enrollment_period_id=uuid4(),
    )

    assert inscripcion.status is EnrollmentStatus.ENROLLED
    assert inscripcion.is_active() is True
    assert inscripcion.cancelled_at is None


@pytest.mark.unit
def test_create_assigns_an_identifier_before_persisting() -> None:
    # El caso de uso necesita el identificador para la respuesta. Esperar a que PostgreSQL lo
    # asignara obligaría a un `flush` intermedio dentro de la transacción crítica.
    inscripcion = Enrollment.create(
        student_id=uuid4(),
        course_offering_id=uuid4(),
        course_id=uuid4(),
        enrollment_period_id=uuid4(),
    )

    assert inscripcion.id is not None


@pytest.mark.unit
def test_create_leaves_the_timestamp_to_the_database() -> None:
    # `enrolled_at` lo pone el `DEFAULT NOW()` de PostgreSQL: es la única fuente horaria
    # fiable cuando varias instancias pueden tener relojes ligeramente distintos.
    inscripcion = Enrollment.create(
        student_id=uuid4(),
        course_offering_id=uuid4(),
        course_id=uuid4(),
        enrollment_period_id=uuid4(),
    )

    assert inscripcion.enrolled_at is None


@pytest.mark.unit
def test_create_links_the_four_identifiers() -> None:
    # La materia viaja junto al grupo desde la migración `0014`: es lo que permite a la base
    # garantizar «una materia, un grupo por período», que un índice sobre el grupo no ve.
    student_id, offering_id, course_id, period_id = uuid4(), uuid4(), uuid4(), uuid4()

    inscripcion = Enrollment.create(
        student_id=student_id,
        course_offering_id=offering_id,
        course_id=course_id,
        enrollment_period_id=period_id,
    )

    assert (
        inscripcion.student_id,
        inscripcion.course_offering_id,
        inscripcion.course_id,
        inscripcion.enrollment_period_id,
    ) == (student_id, offering_id, course_id, period_id)


@pytest.mark.unit
def test_cancel_marks_it_cancelled_and_stamps_the_moment() -> None:
    inscripcion = crear_inscripcion()

    inscripcion.cancel(AHORA)

    assert inscripcion.status is EnrollmentStatus.CANCELLED
    assert inscripcion.cancelled_at == AHORA
    assert inscripcion.is_active() is False


@pytest.mark.unit
def test_cancel_when_already_cancelled_raises() -> None:
    """Cancelar dos veces liberaría el cupo dos veces.

    El segundo `release_slot()` dejaría `enrolled_count` por debajo de la ocupación real, y
    ese hueco fantasma lo podrían tomar dos personas. Es la primera de las dos defensas; la
    segunda es la guarda de `release_slot()`.
    """
    inscripcion = crear_inscripcion(status=EnrollmentStatus.CANCELLED)

    with pytest.raises(EnrollmentAlreadyCancelledError):
        inscripcion.cancel(AHORA)


@pytest.mark.unit
def test_cancel_when_already_cancelled_does_not_move_the_timestamp() -> None:
    momento_original = AHORA - timedelta(days=1)
    inscripcion = crear_inscripcion(
        status=EnrollmentStatus.CANCELLED, cancelled_at=momento_original
    )

    with pytest.raises(EnrollmentAlreadyCancelledError):
        inscripcion.cancel(AHORA)

    assert inscripcion.cancelled_at == momento_original


@pytest.mark.unit
def test_reactivate_revives_a_cancelled_enrollment() -> None:
    # La restricción UNIQUE impide crear una fila nueva al reinscribirse en el mismo grupo,
    # así que se reactiva la existente en vez de duplicar el registro.
    inscripcion = crear_inscripcion(status=EnrollmentStatus.CANCELLED, cancelled_at=AHORA)

    inscripcion.reactivate()

    assert inscripcion.is_active() is True
    assert inscripcion.cancelled_at is None


@pytest.mark.unit
def test_reactivated_enrollment_can_be_cancelled_again() -> None:
    inscripcion = crear_inscripcion(status=EnrollmentStatus.CANCELLED, cancelled_at=AHORA)

    inscripcion.reactivate()
    inscripcion.cancel(AHORA)

    assert inscripcion.status is EnrollmentStatus.CANCELLED


@pytest.mark.unit
def test_a_waitlisted_enrollment_is_not_active() -> None:
    # Ninguna operación produce este estado —la lista de espera es una ausencia intencional—
    # pero si una fila llegara con él, no debe contarse como inscripción vigente.
    assert crear_inscripcion(status=EnrollmentStatus.WAITLISTED).is_active() is False
