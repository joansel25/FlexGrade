"""Pruebas del cierre y consolidación del período (iteración 9.3).

**Es la operación que cierra el ciclo académico y la única IRREVERSIBLE del sistema.** Hasta la
Fase 9, `academic_history` solo la escribía el seed: en producción habría quedado vacía para
siempre, `find_approved_course_ids` habría devuelto vacío y nadie habría cumplido ningún
prerrequisito a partir del segundo semestre.

Por ser irreversible, casi todo lo que se prueba aquí es lo que **impide** consolidar. Los
cuatro rechazos van por separado porque llevan a acciones distintas: no hacer nada, esperar a
que cierre la ventana, perseguir notas que faltan, o revisar un choque con lo ya registrado.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.application.use_cases.admin.consolidate_period import ConsolidatePeriodUseCase
from app.domain.exceptions.admin import (
    AlreadyInAcademicHistoryError,
    PeriodAlreadyConsolidatedError,
    PeriodHasUngradedEnrollmentsError,
    PeriodStillOpenError,
)
from app.domain.exceptions.catalog import PeriodNotFoundError
from app.domain.value_objects.enrollment_status import EnrollmentStatus
from app.domain.value_objects.grade import Grade
from app.domain.value_objects.history_status import HistoryStatus
from tests.unit.doubles import (
    FakeUnitOfWork,
    InMemoryAcademicHistory,
    InMemoryCourseRepository,
    InMemoryEnrollmentRepository,
    InMemoryOfferingRepository,
    InMemoryPeriodRepository,
)
from tests.unit.factories import crear_inscripcion, crear_materia, crear_oferta, crear_periodo

AHORA = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
CERRADA = {"starts_at": AHORA - timedelta(days=60), "ends_at": AHORA - timedelta(days=30)}
ABIERTA = {"starts_at": AHORA - timedelta(days=1), "ends_at": AHORA + timedelta(days=7)}


def _escenario(
    *,
    ventana: dict | None = None,
    consolidado: bool = False,
    notas: list[str | None] | None = None,
    sin_inscripciones: bool = False,
):
    """Un período con dos estudiantes en Cálculo I y una cancelada que no debe viajar."""
    calculo = crear_materia(code="MAT101", name="Cálculo I")
    fisica = crear_materia(code="FIS101", name="Física I")

    periodo = crear_periodo(
        code="2025-2-V1",
        academic_period="2025-2",
        is_active=True,
        **(ventana or CERRADA),
    )

    if consolidado:
        periodo.consolidated_at = AHORA - timedelta(days=1)
        periodo.is_active = False

    grupo = crear_oferta(enrollment_period_id=periodo.id, course_id=calculo.id, group_number="01")
    otro = crear_oferta(enrollment_period_id=periodo.id, course_id=fisica.id, group_number="01")

    ada, zoe = uuid4(), uuid4()
    valores = notas if notas is not None else ["4.20", "2.10"]

    inscripciones = [
        crear_inscripcion(
            student_id=ada,
            course_offering_id=grupo.id,
            enrollment_period_id=periodo.id,
            final_grade=None if valores[0] is None else Grade(Decimal(valores[0])),
        ),
        crear_inscripcion(
            student_id=zoe,
            course_offering_id=grupo.id,
            enrollment_period_id=periodo.id,
            final_grade=None if valores[1] is None else Grade(Decimal(valores[1])),
        ),
        # Cancelada, y con nota: ni siquiera así debe llegar al expediente. Quien dio de baja la
        # materia no la cursó.
        crear_inscripcion(
            student_id=ada,
            course_offering_id=otro.id,
            enrollment_period_id=periodo.id,
            status=EnrollmentStatus.CANCELLED,
            final_grade=Grade(Decimal("5.00")),
        ),
    ]

    historial = InMemoryAcademicHistory()

    caso = ConsolidatePeriodUseCase(
        InMemoryPeriodRepository([periodo]),
        InMemoryEnrollmentRepository([] if sin_inscripciones else inscripciones),
        InMemoryOfferingRepository([grupo, otro]),
        InMemoryCourseRepository([calculo, fisica]),
        historial,
        FakeUnitOfWork(),
        clock=lambda: AHORA,
    )

    return caso, periodo, historial, {"ada": ada, "zoe": zoe, "calculo": calculo}


# ---------------------------------------------------------------------------
# El camino que cierra el ciclo
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_las_notas_pasan_al_historial_con_su_resultado_derivado() -> None:
    """Es lo que hace que el sistema funcione más de un semestre.

    El `status` se DERIVA de la nota y no se recibe: si quien construye el registro pudiera
    decidirlo, un 4.2 podría acabar figurando como perdido.
    """
    caso, periodo, historial, datos = _escenario()

    resumen = caso.execute(periodo.id)

    assert resumen.records == 2
    assert resumen.approved == 1
    assert {(r.student_id, r.status) for r in historial.registros} == {
        (datos["ada"], HistoryStatus.APPROVED),
        (datos["zoe"], HistoryStatus.FAILED),
    }


@pytest.mark.unit
def test_una_inscripcion_cancelada_no_llega_al_expediente() -> None:
    # Aunque tenga nota. Cancelar la borra del semestre, que es la decisión de la Fase 3, y
    # llevarla al historial diría que se cursó.
    caso, periodo, historial, datos = _escenario()

    caso.execute(periodo.id)

    assert all(r.course_id == datos["calculo"].id for r in historial.registros)


@pytest.mark.unit
def test_el_expediente_guarda_la_materia_y_no_el_grupo() -> None:
    # Años después, a quien lee un historial le da igual con qué docente se vio Cálculo I.
    caso, periodo, historial, datos = _escenario()

    caso.execute(periodo.id)

    assert {r.course_id for r in historial.registros} == {datos["calculo"].id}


@pytest.mark.unit
def test_el_periodo_queda_marcado_y_desactivado() -> None:
    """Consolidado y activo a la vez sería el peor estado posible.

    Permitiría matricularse en un semestre cuyo expediente ya se escribió, y esas inscripciones
    no llegarían nunca al historial porque la consolidación ya pasó. La base lo respalda con un
    `CHECK`; la entidad lo hace en un solo gesto para que no pueda olvidarse.
    """
    caso, periodo, _, _ = _escenario()

    caso.execute(periodo.id)

    assert periodo.consolidated_at == AHORA
    assert periodo.is_active is False


# ---------------------------------------------------------------------------
# Los cuatro rechazos
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_no_se_consolida_dos_veces() -> None:
    # Repetirlo duplicaría el expediente. El `UNIQUE` lo rechazaría igual, pero con un error de
    # restricción que no dice qué pasó ni cuándo ocurrió el primer cierre.
    caso, periodo, _, _ = _escenario(consolidado=True)

    with pytest.raises(PeriodAlreadyConsolidatedError):
        caso.execute(periodo.id)


@pytest.mark.unit
def test_no_se_consolida_con_la_ventana_abierta() -> None:
    """Escribiría el expediente de un semestre en el que todavía entra gente.

    Quien se matriculara después no aparecería en el historial, y nadie se enteraría hasta que
    le faltara un prerrequisito años más tarde.
    """
    caso, periodo, _, _ = _escenario(ventana=ABIERTA)

    with pytest.raises(PeriodStillOpenError):
        caso.execute(periodo.id)


@pytest.mark.unit
def test_no_se_consolida_con_notas_pendientes_y_se_dice_de_que_grupos() -> None:
    """No hay valor con el que rellenar una nota que falta.

    Un cero reprobaría a alguien por un trámite pendiente y omitirla dejaría el expediente
    incompleto en silencio. Se nombran los grupos porque el siguiente paso es hablar con esos
    docentes, y un identificador no dice con cuál.
    """
    caso, periodo, historial, _ = _escenario(notas=["4.20", None])

    with pytest.raises(PeriodHasUngradedEnrollmentsError) as error:
        caso.execute(periodo.id)

    assert error.value.details["pending"] == 1
    assert error.value.details["offerings"] == ["MAT101-01"]
    # Y no se escribió NADA: un cierre a medias es peor que uno que no ocurrió.
    assert historial.registros == []


@pytest.mark.unit
def test_no_se_consolida_lo_que_ya_consta_en_ese_semestre() -> None:
    """Dos ventanas del mismo semestre con alguien que cursó la misma materia en las dos.

    El `UNIQUE` lo rechazaría igual, pero un error de restricción en mitad de una transacción
    que escribe miles de filas no dice cuál de todas la rompió.
    """
    caso, periodo, historial, datos = _escenario()
    historial.registrar(
        student_id=datos["ada"], course_id=datos["calculo"].id, academic_period="2025-2"
    )

    with pytest.raises(AlreadyInAcademicHistoryError) as error:
        caso.execute(periodo.id)

    assert error.value.details["courses"] == ["MAT101"]
    assert historial.registros == []


@pytest.mark.unit
def test_un_periodo_que_no_existe_responde_que_no_existe() -> None:
    caso, _, _, _ = _escenario()

    with pytest.raises(PeriodNotFoundError):
        caso.execute(uuid4())


@pytest.mark.unit
def test_un_periodo_sin_inscripciones_se_cierra_igual() -> None:
    # Un semestre sin matrículas es raro pero legítimo, y dejarlo sin cerrar bloquearía el
    # siguiente. Escribe cero registros y marca el período igualmente.
    caso, periodo, historial, _ = _escenario(sin_inscripciones=True)

    resumen = caso.execute(periodo.id)

    assert resumen.records == 0
    assert historial.registros == []
    assert periodo.esta_consolidado()
