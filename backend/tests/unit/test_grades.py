"""Pruebas del registro de notas (iteración 9.2).

**La nota se guarda en la INSCRIPCIÓN, no en `academic_history`.** Es la decisión que gobierna
toda la Fase 9: el historial es un registro consolidado —decide prerrequisitos y aparece en el
expediente— y escribir cada tecleo del docente directamente allí haría irreversible una
corrección tan normal como equivocarse de fila. La nota nace como borrador y la 9.3 la consolida.

Lo que se comprueba es sobre todo lo que se **rechaza**, y que cada rechazo se distinga de los
demás: «no existe», «no es tuyo», «es de otro semestre», «no está inscrito» y «canceló» se
corrigen en cinco sitios distintos, y un único error mandaría a cuatro de los cinco a buscar
donde no está el problema.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.application.use_cases.teaching.manage_grades import (
    GetOfferingRosterUseCase,
    SetGradeUseCase,
)
from app.domain.exceptions.catalog import OfferingNotFoundError
from app.domain.exceptions.enrollment import (
    CannotGradeCancelledEnrollmentError,
    GradingPeriodClosedError,
    OfferingNotAssignedError,
    StudentNotEnrolledError,
)
from app.domain.exceptions.invalid_value import InvalidValueError
from app.domain.value_objects.enrollment_status import EnrollmentStatus
from app.domain.value_objects.grade import Grade
from tests.unit.doubles import (
    FakeUnitOfWork,
    InMemoryCourseRepository,
    InMemoryEnrollmentRepository,
    InMemoryOfferingRepository,
    InMemoryPeriodRepository,
    InMemoryStudentRepository,
)
from tests.unit.factories import (
    crear_estudiante,
    crear_inscripcion,
    crear_materia,
    crear_oferta,
    crear_periodo,
    crear_profesor,
)

AHORA = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# El value object
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("valor", ["0.0", "3.0", "5.0", "2.999"])
def test_una_nota_dentro_de_la_escala_se_acepta(valor: str) -> None:
    assert Grade(Decimal(valor)).value <= Decimal("5.00")


@pytest.mark.unit
@pytest.mark.parametrize("valor", ["-0.1", "5.01", "7.5", "100"])
def test_una_nota_fuera_de_la_escala_se_rechaza(valor: str) -> None:
    """El rango es una regla de negocio, no un formato.

    Una nota de 7.5 no es un dato mal escrito: es una calificación de otra escala, y aceptarla
    dejaría a alguien aprobado según un criterio que el sistema no tiene.
    """
    with pytest.raises(InvalidValueError):
        Grade(Decimal(valor))


@pytest.mark.unit
def test_el_redondeo_favorece_al_estudiante_en_la_frontera() -> None:
    """`2.995` sube a `3.00` y aprueba.

    Python redondea por defecto al par —`ROUND_HALF_EVEN`—, que es correcto para promediar
    dinero y equivocado para decidir el semestre de una persona.
    """
    assert Grade(Decimal("2.995")).value == Decimal("3.00")
    assert Grade(Decimal("2.995")).aprueba()


@pytest.mark.unit
def test_aprueba_desde_tres_y_no_antes() -> None:
    assert not Grade(Decimal("2.99")).aprueba()
    assert Grade(Decimal("3.00")).aprueba()


# ---------------------------------------------------------------------------
# Escenario compartido
# ---------------------------------------------------------------------------


def _escenario(*, estado=EnrollmentStatus.ENROLLED, con_periodo_activo: bool = True):
    """Un grupo de Ana con dos estudiantes inscritos, y un grupo de Beto que no es suyo."""
    ana = crear_profesor(full_name="Ana Pérez", email="ana@tdea.edu.co")
    beto = crear_profesor(full_name="Beto Ruiz", email="beto@tdea.edu.co")

    calculo = crear_materia(code="MAT101", name="Cálculo I")
    activo = crear_periodo(code="2025-2-V1", is_active=con_periodo_activo)

    grupo = crear_oferta(
        enrollment_period_id=activo.id, course_id=calculo.id, group_number="01", professor=ana
    )
    ajeno = crear_oferta(
        enrollment_period_id=activo.id, course_id=calculo.id, group_number="02", professor=beto
    )

    # Zoe antes que Ada en la lista de inscripción, para comprobar que la salida se ordena por
    # nombre y no por el orden en que llegaron.
    zoe = crear_estudiante(student_code="202500002", full_name="Zoe Zapata")
    ada = crear_estudiante(student_code="202500001", full_name="Ada Álvarez")

    inscripciones = [
        crear_inscripcion(
            student_id=zoe.id,
            course_offering_id=grupo.id,
            enrollment_period_id=activo.id,
            status=estado,
        ),
        crear_inscripcion(
            student_id=ada.id,
            course_offering_id=grupo.id,
            enrollment_period_id=activo.id,
            status=EnrollmentStatus.ENROLLED,
        ),
    ]

    return {
        "ana": ana,
        "beto": beto,
        "grupo": grupo,
        "ajeno": ajeno,
        "zoe": zoe,
        "ada": ada,
        "offerings": InMemoryOfferingRepository([grupo, ajeno]),
        "enrollments": InMemoryEnrollmentRepository(inscripciones),
        "students": InMemoryStudentRepository([zoe, ada]),
        "courses": InMemoryCourseRepository([calculo]),
        "periods": InMemoryPeriodRepository([activo]),
    }


def _lista(e):
    return GetOfferingRosterUseCase(
        e["offerings"], e["enrollments"], e["students"], e["courses"], e["periods"]
    )


def _calificar(e):
    return SetGradeUseCase(
        e["offerings"], e["enrollments"], e["periods"], FakeUnitOfWork(), clock=lambda: AHORA
    )


# ---------------------------------------------------------------------------
# La lista del grupo
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_la_lista_sale_ordenada_por_nombre() -> None:
    # Por el orden de inscripción, quien califica tendría que buscar cada fila. La lista se lee
    # de arriba abajo contra un acta, y el acta va por nombre.
    e = _escenario()

    lista = _lista(e).execute(offering_id=e["grupo"].id, professor_id=e["ana"].id)

    assert [entrada.student.full_name for entrada in lista.entries] == [
        "Ada Álvarez",
        "Zoe Zapata",
    ]


@pytest.mark.unit
def test_la_lista_dice_cuantas_faltan_por_calificar() -> None:
    """Es la cifra que le dice al docente si ya terminó.

    Se cuenta aquí y no en la interfaz para que no tenga que recorrer la lista, y sobre todo
    para que la 9.3 y la pantalla usen el mismo número.
    """
    e = _escenario()

    lista = _lista(e).execute(offering_id=e["grupo"].id, professor_id=e["ana"].id)

    assert lista.pending == 2

    _calificar(e).execute(
        offering_id=e["grupo"].id,
        professor_id=e["ana"].id,
        student_id=e["ada"].id,
        grade=Grade(Decimal("4.0")),
    )

    assert _lista(e).execute(offering_id=e["grupo"].id, professor_id=e["ana"].id).pending == 1


@pytest.mark.unit
def test_las_canceladas_no_salen_en_la_lista() -> None:
    # Quien canceló no cursó la materia, y ofrecerla en la lista invitaría a calificar una fila
    # que el dominio va a rechazar.
    e = _escenario(estado=EnrollmentStatus.CANCELLED)

    lista = _lista(e).execute(offering_id=e["grupo"].id, professor_id=e["ana"].id)

    assert [entrada.student.full_name for entrada in lista.entries] == ["Ada Álvarez"]


# ---------------------------------------------------------------------------
# Calificar
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_la_nota_queda_en_la_inscripcion_con_su_instante() -> None:
    e = _escenario()

    _calificar(e).execute(
        offering_id=e["grupo"].id,
        professor_id=e["ana"].id,
        student_id=e["ada"].id,
        grade=Grade(Decimal("4.25")),
    )

    inscripcion = e["enrollments"].find_by_student_and_offering_any_status(
        e["ada"].id, e["grupo"].id
    )
    assert inscripcion is not None
    assert inscripcion.final_grade == Grade(Decimal("4.25"))
    assert inscripcion.graded_at == AHORA


@pytest.mark.unit
def test_volver_a_calificar_corrige_en_vez_de_duplicar() -> None:
    """`PUT` idempotente: equivocarse de nota es lo más normal del mundo.

    Si corregir fuera otra operación, quien califica tendría que saber de antemano cuál pedir, y
    la interfaz consultar la nota actual antes de cada guardado solo para acertar con el verbo.
    """
    e = _escenario()
    caso = _calificar(e)

    for nota in ("4.25", "2.90"):
        caso.execute(
            offering_id=e["grupo"].id,
            professor_id=e["ana"].id,
            student_id=e["ada"].id,
            grade=Grade(Decimal(nota)),
        )

    inscripcion = e["enrollments"].find_by_student_and_offering_any_status(
        e["ada"].id, e["grupo"].id
    )
    assert inscripcion is not None
    assert inscripcion.final_grade == Grade(Decimal("2.90"))


@pytest.mark.unit
def test_no_se_puede_calificar_una_inscripcion_cancelada() -> None:
    """Ocurre de verdad: alguien cancela después de que el docente descargue la lista.

    La nota que se guardara aquí viajaría a `academic_history` en la consolidación de la 9.3
    como si la materia se hubiera cursado, y contaría —o dejaría de contar— como prerrequisito.
    """
    e = _escenario(estado=EnrollmentStatus.CANCELLED)

    with pytest.raises(CannotGradeCancelledEnrollmentError):
        _calificar(e).execute(
            offering_id=e["grupo"].id,
            professor_id=e["ana"].id,
            student_id=e["zoe"].id,
            grade=Grade(Decimal("4.0")),
        )


@pytest.mark.unit
def test_no_se_puede_calificar_a_quien_no_esta_inscrito() -> None:
    e = _escenario()

    with pytest.raises(StudentNotEnrolledError):
        _calificar(e).execute(
            offering_id=e["grupo"].id,
            professor_id=e["ana"].id,
            student_id=uuid4(),
            grade=Grade(Decimal("4.0")),
        )


# ---------------------------------------------------------------------------
# Los tres rechazos del acceso al grupo
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_un_docente_no_puede_tocar_el_grupo_de_otro() -> None:
    """403 y no 404: decir que no existe manda a buscar un error de tecleo.

    Quien ve este mensaje sabe que tiene que hablar con Registro Académico, no revisar la URL.
    """
    e = _escenario()

    with pytest.raises(OfferingNotAssignedError):
        _calificar(e).execute(
            offering_id=e["ajeno"].id,
            professor_id=e["ana"].id,
            student_id=e["ada"].id,
            grade=Grade(Decimal("4.0")),
        )


@pytest.mark.unit
def test_leer_la_lista_de_otro_docente_tambien_se_rechaza() -> None:
    # La comprobación vive en una pieza compartida justamente para que las dos operaciones no
    # puedan separarse: es el tipo de código que se corrige en un sitio y se olvida en el otro.
    e = _escenario()

    with pytest.raises(OfferingNotAssignedError):
        _lista(e).execute(offering_id=e["ajeno"].id, professor_id=e["ana"].id)


@pytest.mark.unit
def test_un_grupo_que_no_existe_responde_que_no_existe() -> None:
    e = _escenario()

    with pytest.raises(OfferingNotFoundError):
        _lista(e).execute(offering_id=uuid4(), professor_id=e["ana"].id)


@pytest.mark.unit
def test_no_se_califica_un_periodo_que_ya_no_esta_activo() -> None:
    """Las notas de un semestre cerrado son historia.

    Cambiarlas recalcularía prerrequisitos que ya se usaron para matricular, y alguien podría
    estar cursando ahora mismo una materia que dejaría de poder cursar.
    """
    e = _escenario(con_periodo_activo=False)

    with pytest.raises(GradingPeriodClosedError):
        _calificar(e).execute(
            offering_id=e["grupo"].id,
            professor_id=e["ana"].id,
            student_id=e["ada"].id,
            grade=Grade(Decimal("4.0")),
        )
