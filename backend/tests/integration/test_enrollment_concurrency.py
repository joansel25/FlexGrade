"""Pruebas de concurrencia de la inscripción.

ESTE ES EL ARCHIVO QUE JUSTIFICA EL PROYECTO. `DEVELOPMENT_WORKFLOW.md` define el criterio de
terminado de la Fase 3 exactamente así: *100 estudiantes concurrentes intentando el mismo último
cupo, exactamente uno lo obtiene, los otros 99 reciben 409*.

Corre con **hilos reales contra PostgreSQL real**. No hay forma de probar esto de otra manera:
lo que se está verificando es precisamente lo que ocurre cuando dos transacciones tocan la misma
fila a la vez, y eso no lo reproduce ningún doble en memoria. Un test con mocks que "pasara"
aquí no diría absolutamente nada.

Cada hilo abre su **propia sesión**. Las sesiones de SQLAlchemy no son seguras entre hilos, y
compartir una haría que el test fallara —o peor, pasara— por razones ajenas a lo que se quiere
medir.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.application.use_cases.enrollment.enroll_student import EnrollStudentUseCase
from app.domain.exceptions.enrollment import CapacityExceededError
from app.infrastructure.persistence.sqlalchemy.models.course_offering import CourseOfferingModel
from app.infrastructure.persistence.sqlalchemy.models.enrollment import EnrollmentModel
from app.infrastructure.persistence.sqlalchemy.models.student import StudentModel
from app.infrastructure.persistence.sqlalchemy.models.user import UserModel
from app.infrastructure.persistence.sqlalchemy.repositories.course_repository import (
    SQLAlchemyCourseRepository,
)
from app.infrastructure.persistence.sqlalchemy.repositories.enrollment_repository import (
    SQLAlchemyEnrollmentRepository,
)
from app.infrastructure.persistence.sqlalchemy.repositories.offering_repository import (
    SQLAlchemyOfferingRepository,
)
from app.infrastructure.persistence.sqlalchemy.repositories.period_repository import (
    SQLAlchemyPeriodRepository,
)
from app.infrastructure.persistence.sqlalchemy.session import get_session_factory
from app.infrastructure.persistence.sqlalchemy.unit_of_work import SQLAlchemyUnitOfWork
from tests.integration.conftest import CatalogoDePrueba
from tests.unit.doubles import InMemoryCacheService


@dataclass(frozen=True)
class Resultado:
    """Lo que le pasó a un hilo."""

    exito: bool
    error: str | None


def _inscribir_en_hilo(
    student_id: UUID, offering_id: UUID, barrera: threading.Barrier
) -> Resultado:
    """Ejecuta una inscripción completa en una sesión propia.

    La barrera es la pieza que hace real la prueba: los 100 hilos se detienen aquí y solo
    continúan cuando el último ha llegado. Sin ella, el sistema operativo iría lanzándolos poco
    a poco y en la práctica se ejecutarían casi en serie, sin llegar a competir por la fila. La
    contención se estaría suponiendo, no provocando.
    """
    session: Session = get_session_factory()()

    try:
        caso = EnrollStudentUseCase(
            SQLAlchemyEnrollmentRepository(session),
            SQLAlchemyOfferingRepository(session),
            SQLAlchemyPeriodRepository(session),
            SQLAlchemyCourseRepository(session),
            SQLAlchemyUnitOfWork(session),
            # Caché en memoria y propia de cada hilo: lo que se mide es el bloqueo en
            # PostgreSQL, y meter Redis por medio añadiría una variable ajena al experimento.
            InMemoryCacheService(),
        )

        barrera.wait()

        try:
            caso.execute(student_id=student_id, course_offering_id=offering_id)
            return Resultado(exito=True, error=None)
        except CapacityExceededError:
            return Resultado(exito=False, error="CAPACITY")
        except Exception as inesperado:  # noqa: BLE001
            # Cualquier otra excepción es un defecto, no un resultado esperado. Se captura para
            # que el test la reporte con su tipo en vez de perderse dentro del pool de hilos.
            return Resultado(exito=False, error=f"{type(inesperado).__name__}: {inesperado}")
    finally:
        session.close()


def _crear_estudiantes(db_session: Session, program_id: UUID, cuantos: int) -> list[UUID]:
    """Crea `cuantos` estudiantes distintos, cada uno con su cuenta.

    Tienen que ser personas distintas: si todos los hilos usaran el mismo estudiante, la
    restricción `UNIQUE` de `enrollments` rechazaría los duplicados y el test estaría midiendo
    esa restricción en vez del bloqueo optimista.
    """
    ids: list[UUID] = []

    for numero in range(cuantos):
        usuario = UserModel(
            id=uuid4(),
            email=f"concurrente{numero:03d}@tdea.edu.co",
            password_hash="no-se-usa-en-este-test",
            role="STUDENT",
            is_active=True,
        )
        db_session.add(usuario)
        db_session.flush()

        estudiante = StudentModel(
            id=uuid4(),
            user_id=usuario.id,
            student_code=f"9{numero:06d}",
            program_id=program_id,
            current_semester=1,
            full_name=f"Estudiante Concurrente {numero:03d}",
            enrollment_date=date(2022, 1, 15),
        )
        db_session.add(estudiante)
        ids.append(estudiante.id)

    db_session.commit()
    return ids


def _fijar_cupo(db_session: Session, offering_id: UUID, ocupados: int, capacidad: int) -> None:
    """Deja el grupo con la ocupación exacta que el escenario necesita."""
    db_session.execute(
        text(
            "UPDATE course_offerings "
            "SET enrolled_count = :ocupados, total_capacity = :capacidad "
            "WHERE id = :id"
        ),
        {"ocupados": ocupados, "capacidad": capacidad, "id": offering_id},
    )
    db_session.commit()


def _ejecutar_en_paralelo(
    estudiantes: list[UUID], offering_id: UUID
) -> tuple[list[Resultado], int]:
    """Lanza una inscripción por estudiante, todas a la vez.

    Returns:
        Los resultados y cuántos tuvieron éxito.
    """
    barrera = threading.Barrier(len(estudiantes))

    with ThreadPoolExecutor(max_workers=len(estudiantes)) as pool:
        resultados = list(
            pool.map(
                lambda student_id: _inscribir_en_hilo(student_id, offering_id, barrera),
                estudiantes,
            )
        )

    return resultados, sum(1 for r in resultados if r.exito)


# ---------------------------------------------------------------------------
# El criterio de terminado de la Fase 3
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_one_hundred_students_racing_for_the_last_seat_exactly_one_wins(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    """100 concurrentes al último cupo: gana exactamente uno.

    Es el criterio de terminado literal de `DEVELOPMENT_WORKFLOW.md`. Si este test falla, el
    sistema no cumple su razón de existir: dos personas creerían tener la misma plaza.
    """
    ofertante = catalogo.offering_grupo_01_id
    _fijar_cupo(db_session, ofertante, ocupados=39, capacidad=40)
    estudiantes = _crear_estudiantes(db_session, catalogo.program_id, 100)

    resultados, exitosos = _ejecutar_en_paralelo(estudiantes, ofertante)

    inesperados = [r.error for r in resultados if r.error not in (None, "CAPACITY")]
    assert not inesperados, f"errores no previstos: {inesperados[:5]}"
    assert exitosos == 1, f"ganaron {exitosos} en vez de 1"
    assert sum(1 for r in resultados if r.error == "CAPACITY") == 99


@pytest.mark.integration
def test_after_the_race_the_group_is_exactly_full_never_oversold(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    """El contador acaba exactamente en la capacidad, ni uno más.

    Es la otra mitad de la garantía: no basta con que la API rechace a los 99, el estado
    persistido tiene que ser coherente. Un `enrolled_count` de 41 en una capacidad de 40
    significaría que alguien tiene una plaza que no existe.
    """
    ofertante = catalogo.offering_grupo_01_id
    _fijar_cupo(db_session, ofertante, ocupados=39, capacidad=40)
    estudiantes = _crear_estudiantes(db_session, catalogo.program_id, 100)

    _ejecutar_en_paralelo(estudiantes, ofertante)

    db_session.expire_all()
    grupo = db_session.get(CourseOfferingModel, ofertante)
    assert grupo is not None
    assert grupo.enrolled_count == 40
    assert grupo.enrolled_count <= grupo.total_capacity


@pytest.mark.integration
def test_the_seat_count_matches_the_enrollments_actually_created(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    """El cupo descontado y las inscripciones creadas cuadran.

    Comprueba la atomicidad del `UnitOfWork`. Un cupo descontado sin su inscripción, o al
    revés, sería un estado imposible que ningún `CHECK` detectaría —cada fila por separado
    sería válida— y solo se notaría al cuadrar las dos tablas, que es lo que hace este test.
    """
    ofertante = catalogo.offering_grupo_01_id
    _fijar_cupo(db_session, ofertante, ocupados=39, capacidad=40)
    estudiantes = _crear_estudiantes(db_session, catalogo.program_id, 100)

    _ejecutar_en_paralelo(estudiantes, ofertante)

    db_session.expire_all()
    grupo = db_session.get(CourseOfferingModel, ofertante)
    assert grupo is not None

    creadas = db_session.execute(
        select(func.count())
        .select_from(EnrollmentModel)
        .where(EnrollmentModel.course_offering_id == ofertante)
        .where(EnrollmentModel.status == "ENROLLED")
    ).scalar_one()

    # El grupo partía de 39 ocupados que no tienen fila en `enrollments` —los puso la fixture
    # directamente—, así que las inscripciones creadas son el incremento del contador.
    assert creadas == grupo.enrolled_count - 39


# ---------------------------------------------------------------------------
# El caso intermedio: donde de verdad se calibran los reintentos
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_one_hundred_students_for_fifty_seats_exactly_fifty_win(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    """100 concurrentes para 50 cupos: entran exactamente 50.

    Este escenario es más exigente que el del último cupo, aunque no lo parezca. Allí basta un
    reintento: quien pierde relee el grupo lleno y se rinde de inmediato. Aquí hay cupos de
    sobra, así que los conflictos de versión se encadenan ronda tras ronda y el número de
    reintentos sí se pone a prueba.

    Si `MAX_REINTENTOS` se quedara corto, este test lo detectaría: entrarían MENOS de 50, y
    alguien habría recibido un 409 teniendo cupo disponible. Es la forma de medir ese límite en
    vez de suponerlo.
    """
    ofertante = catalogo.offering_grupo_01_id
    _fijar_cupo(db_session, ofertante, ocupados=0, capacidad=50)
    estudiantes = _crear_estudiantes(db_session, catalogo.program_id, 100)

    resultados, exitosos = _ejecutar_en_paralelo(estudiantes, ofertante)

    inesperados = [r.error for r in resultados if r.error not in (None, "CAPACITY")]
    assert not inesperados, f"errores no previstos: {inesperados[:5]}"
    assert exitosos == 50, (
        f"entraron {exitosos} de 50 cupos. Si es menor, MAX_REINTENTOS se queda corto bajo "
        f"esta contención y alguien recibió un 409 teniendo cupo."
    )

    db_session.expire_all()
    grupo = db_session.get(CourseOfferingModel, ofertante)
    assert grupo is not None
    assert grupo.enrolled_count == 50


@pytest.mark.integration
def test_when_there_is_room_for_everyone_nobody_is_rejected(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    """40 concurrentes con 100 cupos: entran los 40.

    Sin contención por capacidad, pero con 40 transacciones peleando por la misma fila. Es el
    caso donde un bloqueo optimista mal implementado rechazaría a alguien sin motivo.
    """
    ofertante = catalogo.offering_grupo_01_id
    _fijar_cupo(db_session, ofertante, ocupados=0, capacidad=100)
    estudiantes = _crear_estudiantes(db_session, catalogo.program_id, 40)

    resultados, exitosos = _ejecutar_en_paralelo(estudiantes, ofertante)

    inesperados = [r.error for r in resultados if r.error not in (None, "CAPACITY")]
    assert not inesperados, f"errores no previstos: {inesperados[:5]}"
    assert exitosos == 40, f"entraron {exitosos} de 40, habiendo 100 cupos"


@pytest.mark.integration
def test_a_full_group_rejects_everyone(db_session: Session, catalogo: CatalogoDePrueba) -> None:
    """Grupo ya lleno: no entra nadie y el contador no se mueve."""
    ofertante = catalogo.offering_grupo_01_id
    _fijar_cupo(db_session, ofertante, ocupados=40, capacidad=40)
    estudiantes = _crear_estudiantes(db_session, catalogo.program_id, 30)

    _resultados, exitosos = _ejecutar_en_paralelo(estudiantes, ofertante)

    assert exitosos == 0

    db_session.expire_all()
    grupo = db_session.get(CourseOfferingModel, ofertante)
    assert grupo is not None
    assert grupo.enrolled_count == 40
