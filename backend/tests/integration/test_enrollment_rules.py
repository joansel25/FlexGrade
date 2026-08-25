"""Pruebas de integración de las reglas académicas de la inscripción.

Los tests unitarios comprueban que cada servicio decide bien y que el caso de uso los invoca.
Aquí se verifica lo único que aquellos no pueden: que las **consultas** que alimentan esas
decisiones traen los datos correctos de PostgreSQL. Un validador impecable alimentado por un
`WHERE` equivocado rechaza a quien no debe.
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.application.use_cases.enrollment.enroll_student import EnrollStudentUseCase
from app.domain.exceptions.enrollment import (
    CorequisitesNotMetError,
    CourseNotInProgramError,
    PrerequisitesNotMetError,
    ScheduleConflictError,
)
from app.infrastructure.persistence.sqlalchemy.models.academic_history import AcademicHistoryModel
from app.infrastructure.persistence.sqlalchemy.models.course import CourseModel
from app.infrastructure.persistence.sqlalchemy.models.course_offering import CourseOfferingModel
from app.infrastructure.persistence.sqlalchemy.models.program_course_requirement import (
    ProgramCourseRequirementModel,
)
from app.infrastructure.persistence.sqlalchemy.models.schedule_block import ScheduleBlockModel
from app.infrastructure.persistence.sqlalchemy.models.student import StudentModel
from app.infrastructure.persistence.sqlalchemy.models.user import UserModel
from app.infrastructure.persistence.sqlalchemy.repositories.academic_history_repository import (
    SQLAlchemyAcademicHistoryRepository,
)
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
from app.infrastructure.persistence.sqlalchemy.repositories.student_repository import (
    SQLAlchemyStudentRepository,
)
from app.infrastructure.persistence.sqlalchemy.unit_of_work import SQLAlchemyUnitOfWork
from tests.integration.conftest import CatalogoDePrueba
from tests.unit.doubles import InMemoryCacheService


def _caso(session: Session) -> EnrollStudentUseCase:
    """Monta el caso de uso con todos los adaptadores reales."""
    return EnrollStudentUseCase(
        SQLAlchemyEnrollmentRepository(session),
        SQLAlchemyOfferingRepository(session),
        SQLAlchemyPeriodRepository(session),
        SQLAlchemyCourseRepository(session),
        SQLAlchemyStudentRepository(session),
        SQLAlchemyAcademicHistoryRepository(session),
        SQLAlchemyUnitOfWork(session),
        InMemoryCacheService(),
    )


def _crear_estudiante(session: Session, program_id: UUID, sufijo: str = "01") -> UUID:
    """Crea un estudiante con su cuenta y devuelve su identificador."""
    usuario = UserModel(
        id=uuid4(),
        email=f"reglas{sufijo}@tdea.edu.co",
        password_hash="no-se-usa",
        role="STUDENT",
        is_active=True,
    )
    session.add(usuario)
    session.flush()

    estudiante = StudentModel(
        id=uuid4(),
        user_id=usuario.id,
        student_code=f"70000{sufijo}",
        program_id=program_id,
        current_semester=3,
        full_name=f"Estudiante Reglas {sufijo}",
        enrollment_date=date(2022, 1, 15),
    )
    session.add(estudiante)
    session.commit()
    return estudiante.id


# ---------------------------------------------------------------------------
# Plan de estudios
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_enroll_in_a_course_from_another_program_is_rejected(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    """La materia existe y tiene cupo, pero no está en el plan de esta persona."""
    from app.infrastructure.persistence.sqlalchemy.models.program import ProgramModel

    otro_programa = ProgramModel(id=uuid4(), code="DERE", name="Derecho", total_semesters=10)
    db_session.add(otro_programa)
    db_session.commit()
    estudiante_id = _crear_estudiante(db_session, otro_programa.id)

    with pytest.raises(CourseNotInProgramError):
        _caso(db_session).execute(
            student_id=estudiante_id, course_offering_id=catalogo.offering_grupo_01_id
        )


@pytest.mark.integration
def test_enroll_in_a_course_from_the_own_program_is_allowed(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    estudiante_id = _crear_estudiante(db_session, catalogo.program_id)

    resultado = _caso(db_session).execute(
        student_id=estudiante_id, course_offering_id=catalogo.offering_grupo_01_id
    )

    assert resultado.course_code == "MAT101"


# ---------------------------------------------------------------------------
# Prerrequisitos, contra el historial real
# ---------------------------------------------------------------------------


def _ofrecer_calculo_ii(db_session: Session, catalogo: CatalogoDePrueba) -> UUID:
    """Abre un grupo de MAT102 y devuelve su identificador.

    La fixture `catalogo` ya deja MAT102 en el plan de estudios del programa y enlazada a
    MAT101 en `program_course_requirements`; lo único que falta es que se ofrezca este semestre.
    """
    grupo = CourseOfferingModel(
        id=uuid4(),
        enrollment_period_id=catalogo.period_id,
        course_id=catalogo.calculo_ii_id,
        group_number="01",
        total_capacity=40,
        enrolled_count=0,
    )
    db_session.add(grupo)
    db_session.commit()
    return grupo.id


@pytest.mark.integration
def test_enroll_without_having_approved_the_prerequisite_is_rejected(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    # La fixture ya enlaza MAT102 -> MAT101 como PRERREQUISITO en el plan de Ingeniería.
    grupo_id = _ofrecer_calculo_ii(db_session, catalogo)
    estudiante_id = _crear_estudiante(db_session, catalogo.program_id)

    with pytest.raises(PrerequisitesNotMetError) as error:
        _caso(db_session).execute(student_id=estudiante_id, course_offering_id=grupo_id)

    assert error.value.details["missing_prerequisites"] == ["MAT101"]


@pytest.mark.integration
def test_enroll_after_approving_the_prerequisite_succeeds(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    grupo_id = _ofrecer_calculo_ii(db_session, catalogo)
    estudiante_id = _crear_estudiante(db_session, catalogo.program_id)
    db_session.add(
        AcademicHistoryModel(
            student_id=estudiante_id,
            course_id=catalogo.calculo_i_id,
            academic_period="2025-1",
            final_grade=Decimal("4.20"),
            status="APPROVED",
        )
    )
    db_session.commit()

    resultado = _caso(db_session).execute(student_id=estudiante_id, course_offering_id=grupo_id)

    assert resultado.course_code == "MAT102"


@pytest.mark.integration
@pytest.mark.parametrize("estado", ["FAILED", "WITHDRAWN"])
def test_a_failed_or_withdrawn_course_does_not_satisfy_the_prerequisite(
    db_session: Session, catalogo: CatalogoDePrueba, estado: str
) -> None:
    """Solo `APPROVED` habilita.

    Es la consulta que este test verifica de verdad: si el `WHERE status = 'APPROVED'` del
    repositorio faltara, haber perdido la materia contaría como haberla aprobado.
    """
    grupo_id = _ofrecer_calculo_ii(db_session, catalogo)
    estudiante_id = _crear_estudiante(db_session, catalogo.program_id)
    db_session.add(
        AcademicHistoryModel(
            student_id=estudiante_id,
            course_id=catalogo.calculo_i_id,
            academic_period="2025-1",
            final_grade=Decimal("2.00") if estado == "FAILED" else None,
            status=estado,
        )
    )
    db_session.commit()

    with pytest.raises(PrerequisitesNotMetError):
        _caso(db_session).execute(student_id=estudiante_id, course_offering_id=grupo_id)


@pytest.mark.integration
def test_the_history_of_another_student_does_not_count(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    # Si el `WHERE student_id = :id` faltara, cualquiera se beneficiaría de lo que aprobó otro.
    grupo_id = _ofrecer_calculo_ii(db_session, catalogo)
    con_historial = _crear_estudiante(db_session, catalogo.program_id, sufijo="01")
    sin_historial = _crear_estudiante(db_session, catalogo.program_id, sufijo="02")
    db_session.add(
        AcademicHistoryModel(
            student_id=con_historial,
            course_id=catalogo.calculo_i_id,
            academic_period="2025-1",
            final_grade=Decimal("4.50"),
            status="APPROVED",
        )
    )
    db_session.commit()

    with pytest.raises(PrerequisitesNotMetError):
        _caso(db_session).execute(student_id=sin_historial, course_offering_id=grupo_id)


@pytest.mark.integration
def test_a_course_with_a_prerequisite_needs_it_but_one_without_does_not(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    # MAT101 no exige nada, así que se inscribe sin historial alguno.
    estudiante_id = _crear_estudiante(db_session, catalogo.program_id)

    resultado = _caso(db_session).execute(
        student_id=estudiante_id, course_offering_id=catalogo.offering_grupo_01_id
    )

    assert resultado.course_code == "MAT101"


# ---------------------------------------------------------------------------
# Choque de horario, con las franjas reales
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_enrolling_in_two_groups_at_the_same_time_is_rejected(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    """El grupo 01 se dicta lunes de 8 a 10. Se abre otro que solapa."""
    solapado = CourseOfferingModel(
        id=uuid4(),
        enrollment_period_id=catalogo.period_id,
        course_id=catalogo.calculo_ii_id,
        group_number="01",
        total_capacity=40,
        enrolled_count=0,
    )
    db_session.add(solapado)
    db_session.flush()
    db_session.add(
        ScheduleBlockModel(
            course_offering_id=solapado.id,
            day_of_week=1,
            start_time=time(9, 0),
            end_time=time(11, 0),
        )
    )
    # Se le quita el prerrequisito para que el rechazo sea por horario y no por MAT101.
    db_session.query(ProgramCourseRequirementModel).filter_by(
        course_id=catalogo.calculo_ii_id
    ).delete()
    db_session.commit()

    estudiante_id = _crear_estudiante(db_session, catalogo.program_id)
    caso = _caso(db_session)
    caso.execute(student_id=estudiante_id, course_offering_id=catalogo.offering_grupo_01_id)

    with pytest.raises(ScheduleConflictError) as error:
        caso.execute(student_id=estudiante_id, course_offering_id=solapado.id)

    assert error.value.details["conflicting_offering_id"] == str(catalogo.offering_grupo_01_id)


@pytest.mark.integration
def test_enrolling_in_two_groups_at_different_times_is_allowed(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    sin_choque = CourseOfferingModel(
        id=uuid4(),
        enrollment_period_id=catalogo.period_id,
        course_id=catalogo.calculo_ii_id,
        group_number="01",
        total_capacity=40,
        enrolled_count=0,
    )
    db_session.add(sin_choque)
    db_session.flush()
    db_session.add(
        ScheduleBlockModel(
            course_offering_id=sin_choque.id,
            day_of_week=5,
            start_time=time(14, 0),
            end_time=time(16, 0),
        )
    )
    db_session.query(ProgramCourseRequirementModel).filter_by(
        course_id=catalogo.calculo_ii_id
    ).delete()
    db_session.commit()

    estudiante_id = _crear_estudiante(db_session, catalogo.program_id)
    caso = _caso(db_session)
    caso.execute(student_id=estudiante_id, course_offering_id=catalogo.offering_grupo_01_id)

    resultado = caso.execute(student_id=estudiante_id, course_offering_id=sin_choque.id)

    assert resultado.course_code == "MAT102"


@pytest.mark.integration
def test_a_group_without_a_schedule_never_clashes(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    # El grupo 02 de la fixture no tiene franjas publicadas.
    materia = db_session.get(CourseModel, catalogo.calculo_i_id)
    assert materia is not None

    estudiante_id = _crear_estudiante(db_session, catalogo.program_id)
    caso = _caso(db_session)
    caso.execute(student_id=estudiante_id, course_offering_id=catalogo.offering_grupo_01_id)

    resultado = caso.execute(
        student_id=estudiante_id, course_offering_id=catalogo.offering_grupo_02_id
    )

    assert resultado.group_number == "02"


# ---------------------------------------------------------------------------
# Correquisitos, contra las inscripciones vivas del período (iteración 6.2)
# ---------------------------------------------------------------------------


def _ofrecer(
    db_session: Session, catalogo: CatalogoDePrueba, course_id: UUID, grupo: str = "01"
) -> UUID:
    """Abre un grupo sin horario de la materia indicada y devuelve su identificador.

    Sin franjas a propósito: estos tests van sobre correquisitos, y un choque de horario
    accidental los haría fallar por un motivo que no es el que están comprobando.
    """
    oferta = CourseOfferingModel(
        id=uuid4(),
        enrollment_period_id=catalogo.period_id,
        course_id=course_id,
        group_number=grupo,
        total_capacity=40,
        enrolled_count=0,
    )
    db_session.add(oferta)
    db_session.commit()
    return oferta.id


@pytest.mark.integration
def test_a_simple_corequisite_must_be_enrolled_in_the_same_period(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    """Un correquisito NO mutuo sí tiene que estar ya inscrito.

    La fixture declara el par mutuo MAT101 <-> TAL101; aquí se añade una tercera regla en un
    solo sentido —MAT102 exige cursar el taller a la vez— para comprobar que la exención del
    bloqueo circular se aplica SOLO a los pares recíprocos y no a cualquier correquisito.
    """
    db_session.query(ProgramCourseRequirementModel).filter_by(
        course_id=catalogo.calculo_ii_id
    ).delete()
    db_session.add(
        ProgramCourseRequirementModel(
            program_id=catalogo.program_id,
            course_id=catalogo.calculo_ii_id,
            required_course_id=catalogo.taller_id,
            requirement_type="COREQUISITE",
        )
    )
    db_session.commit()

    grupo_id = _ofrecer(db_session, catalogo, catalogo.calculo_ii_id)
    estudiante_id = _crear_estudiante(db_session, catalogo.program_id)

    with pytest.raises(CorequisitesNotMetError) as error:
        _caso(db_session).execute(student_id=estudiante_id, course_offering_id=grupo_id)

    assert error.value.details["missing_corequisites"] == ["TAL101"]


@pytest.mark.integration
def test_a_simple_corequisite_already_enrolled_lets_the_enrollment_through(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    db_session.query(ProgramCourseRequirementModel).filter_by(
        course_id=catalogo.calculo_ii_id
    ).delete()
    db_session.add(
        ProgramCourseRequirementModel(
            program_id=catalogo.program_id,
            course_id=catalogo.calculo_ii_id,
            required_course_id=catalogo.taller_id,
            requirement_type="COREQUISITE",
        )
    )
    db_session.commit()

    taller_grupo = _ofrecer(db_session, catalogo, catalogo.taller_id)
    calculo_ii_grupo = _ofrecer(db_session, catalogo, catalogo.calculo_ii_id, grupo="02")
    estudiante_id = _crear_estudiante(db_session, catalogo.program_id)
    caso = _caso(db_session)

    caso.execute(student_id=estudiante_id, course_offering_id=taller_grupo)
    resultado = caso.execute(student_id=estudiante_id, course_offering_id=calculo_ii_grupo)

    assert resultado.course_code == "MAT102"


@pytest.mark.integration
def test_a_mutual_corequisite_block_can_be_enrolled_one_course_at_a_time(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    """El caso que da sentido a la iteración: MAT101 y TAL101 se exigen la una a la otra.

    Si el validador exigiera que la otra estuviera inscrita ANTES, la primera de las dos
    fallaría siempre y el bloque sería imposible de matricular por cualquier camino. Validando
    el conjunto, cualquiera de ellas puede entrar primero.
    """
    taller_grupo = _ofrecer(db_session, catalogo, catalogo.taller_id)
    estudiante_id = _crear_estudiante(db_session, catalogo.program_id)
    caso = _caso(db_session)

    primera = caso.execute(
        student_id=estudiante_id, course_offering_id=catalogo.offering_grupo_02_id
    )
    segunda = caso.execute(student_id=estudiante_id, course_offering_id=taller_grupo)

    assert primera.course_code == "MAT101"
    assert segunda.course_code == "TAL101"


@pytest.mark.integration
def test_a_corequisite_declared_in_another_program_does_not_apply(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    """La regla que rige es la del plan del ESTUDIANTE, no la de cualquier plan.

    Cálculo I exige el taller en Ingeniería y no exige nada en Administración. Un estudiante de
    Administración se inscribe sin encontrarse una regla que no es suya, que era imposible de
    expresar con la tabla anterior.
    """
    grupo_id = _ofrecer(db_session, catalogo, catalogo.calculo_i_id, grupo="07")
    estudiante_id = _crear_estudiante(db_session, catalogo.otro_program_id, sufijo="99")

    resultado = _caso(db_session).execute(student_id=estudiante_id, course_offering_id=grupo_id)

    assert resultado.course_code == "MAT101"
