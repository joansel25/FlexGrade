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
    CourseNotInProgramError,
    PrerequisitesNotMetError,
    ScheduleConflictError,
)
from app.infrastructure.persistence.sqlalchemy.models.academic_history import AcademicHistoryModel
from app.infrastructure.persistence.sqlalchemy.models.course import CourseModel
from app.infrastructure.persistence.sqlalchemy.models.course_offering import CourseOfferingModel
from app.infrastructure.persistence.sqlalchemy.models.course_prerequisite import (
    CoursePrerequisiteModel,
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
    MAT101 en `course_prerequisites`; lo único que falta es que se ofrezca este semestre.
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
    # La fixture ya enlaza MAT102 -> MAT101 en `course_prerequisites`.
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
    db_session.query(CoursePrerequisiteModel).filter_by(course_id=catalogo.calculo_ii_id).delete()
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
    db_session.query(CoursePrerequisiteModel).filter_by(course_id=catalogo.calculo_ii_id).delete()
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
