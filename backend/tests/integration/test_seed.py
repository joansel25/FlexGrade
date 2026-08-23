"""Pruebas de integración del script de datos de ejemplo.

La idempotencia es lo único que hay que probar aquí a fondo, y solo se puede probar contra
PostgreSQL real: lo que impide los duplicados son las restricciones `UNIQUE` del esquema, y
un doble en memoria no las tiene. Un seed que falla en la segunda ejecución es un seed que
nadie se atreve a ejecutar.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infrastructure.persistence.sqlalchemy.models.administrator import AdministratorModel
from app.infrastructure.persistence.sqlalchemy.models.course import CourseModel
from app.infrastructure.persistence.sqlalchemy.models.course_offering import CourseOfferingModel
from app.infrastructure.persistence.sqlalchemy.models.course_prerequisite import (
    CoursePrerequisiteModel,
)
from app.infrastructure.persistence.sqlalchemy.models.enrollment_period import EnrollmentPeriodModel
from app.infrastructure.persistence.sqlalchemy.models.professor import ProfessorModel
from app.infrastructure.persistence.sqlalchemy.models.program import ProgramModel
from app.infrastructure.persistence.sqlalchemy.models.program_course import ProgramCourseModel
from app.infrastructure.persistence.sqlalchemy.models.schedule_block import ScheduleBlockModel
from app.infrastructure.persistence.sqlalchemy.models.student import StudentModel
from app.infrastructure.persistence.sqlalchemy.models.user import UserModel
from app.infrastructure.seed import CORREO_ADMIN, PASSWORD_DE_EJEMPLO, sembrar

# Volúmenes que fija `docs/DATA_MODEL.md` sección 4.
ESPERADO = {
    ProgramModel: 3,
    ProfessorModel: 10,
    CourseModel: 15,
    CourseOfferingModel: 20,
    StudentModel: 50,
}


def _contar(session: Session, modelo: type) -> int:
    return int(session.execute(select(func.count()).select_from(modelo)).scalar_one())


@pytest.mark.integration
def test_seed_creates_the_documented_volumes(db_session: Session) -> None:
    sembrar(db_session)
    db_session.commit()

    for modelo, cuantos in ESPERADO.items():
        assert _contar(db_session, modelo) == cuantos, modelo.__name__


@pytest.mark.integration
def test_seed_is_idempotent(db_session: Session) -> None:
    """Ejecutarlo tres veces deja lo mismo que ejecutarlo una.

    Es la propiedad que promete su docstring y la que permite usarlo como paso rutinario tras
    levantar el entorno sin tener que recordar si ya estaba sembrado.
    """
    sembrar(db_session)
    db_session.commit()
    primera = {m: _contar(db_session, m) for m in ESPERADO}

    for _ in range(2):
        sembrar(db_session)
        db_session.commit()

    assert {m: _contar(db_session, m) for m in ESPERADO} == primera


@pytest.mark.integration
def test_seed_does_not_duplicate_the_secondary_tables(db_session: Session) -> None:
    # Las tablas de asociación son las que más fácilmente se duplican, porque su clave es
    # compuesta y no salta a la vista.
    sembrar(db_session)
    db_session.commit()
    antes = {
        m: _contar(db_session, m)
        for m in (
            ProgramCourseModel,
            CoursePrerequisiteModel,
            ScheduleBlockModel,
            EnrollmentPeriodModel,
            AdministratorModel,
        )
    }

    sembrar(db_session)
    db_session.commit()

    assert {m: _contar(db_session, m) for m in antes} == antes


@pytest.mark.integration
def test_seed_does_not_overwrite_existing_data(db_session: Session) -> None:
    """Lo que ya existe se respeta.

    Si estabas probando algo y cambiaste un cupo a mano, volver a sembrar no debe revertirlo:
    perder el estado de una prueba en curso por ejecutar un comando de rutina es exactamente
    lo que hace que la gente deje de confiar en la herramienta.
    """
    sembrar(db_session)
    db_session.commit()

    grupo = db_session.execute(select(CourseOfferingModel).limit(1)).scalar_one()
    grupo.enrolled_count = 17
    db_session.commit()
    grupo_id = grupo.id

    sembrar(db_session)
    db_session.commit()

    db_session.expire_all()
    assert db_session.get(CourseOfferingModel, grupo_id).enrolled_count == 17  # type: ignore[union-attr]


@pytest.mark.integration
def test_seed_creates_only_one_active_period(db_session: Session) -> None:
    # El índice único parcial lo impediría, así que si el seed lo intentara, fallaría con un
    # error de clave duplicada en la segunda ejecución.
    sembrar(db_session)
    db_session.commit()
    sembrar(db_session)
    db_session.commit()

    activos = db_session.execute(
        select(func.count())
        .select_from(EnrollmentPeriodModel)
        .where(EnrollmentPeriodModel.is_active.is_(True))
    ).scalar_one()

    assert activos == 1


@pytest.mark.integration
def test_seeded_period_is_open_right_now(db_session: Session) -> None:
    # Las fechas se calculan alrededor del instante actual, no fijas en 2025: un período que
    # naciera cerrado obligaría a tocar la base a mano antes de poder probar nada.
    sembrar(db_session)
    db_session.commit()

    periodo = db_session.execute(
        select(EnrollmentPeriodModel).where(EnrollmentPeriodModel.is_active.is_(True))
    ).scalar_one()

    ahora = db_session.execute(select(func.now())).scalar_one()

    assert periodo.starts_at <= ahora <= periodo.ends_at


@pytest.mark.integration
def test_seeded_accounts_can_authenticate(db_session: Session) -> None:
    """Las contraseñas sembradas son verificables.

    Guardar un hash que luego no valide dejaría 51 cuentas inservibles y el fallo solo
    aparecería al intentar iniciar sesión.
    """
    from app.infrastructure.auth.jwt_auth_service import JWTAuthService
    from app.infrastructure.config.settings import get_settings

    sembrar(db_session)
    db_session.commit()

    hasher = JWTAuthService(get_settings())
    admin = db_session.execute(
        select(UserModel).where(UserModel.email == CORREO_ADMIN)
    ).scalar_one()

    assert admin.role == "ADMIN"
    assert hasher.verify(PASSWORD_DE_EJEMPLO, admin.password_hash)


@pytest.mark.integration
def test_seeded_prerequisite_chain_is_linked(db_session: Session) -> None:
    # MAT101 -> MAT102 -> MAT201: la cadena que la Fase 3 usará para probar la validación de
    # prerrequisitos en más de un nivel.
    sembrar(db_session)
    db_session.commit()

    materias = {
        c.code: c
        for c in db_session.execute(
            select(CourseModel).where(CourseModel.code.in_(["MAT101", "MAT102", "MAT201"]))
        ).scalars()
    }

    enlaces = {
        (p.course_id, p.required_course_id)
        for p in db_session.execute(select(CoursePrerequisiteModel)).scalars()
    }

    assert (materias["MAT102"].id, materias["MAT101"].id) in enlaces
    assert (materias["MAT201"].id, materias["MAT102"].id) in enlaces


@pytest.mark.integration
def test_some_courses_are_deliberately_not_offered(db_session: Session) -> None:
    """No toda materia se dicta cada semestre, y el catálogo tiene que poder decirlo.

    Sin al menos una materia sin grupo, `GET /courses/{id}/offerings` no tendría forma de
    probar su caso más sutil: devolver 200 con una lista vacía —un resultado legítimo— en vez
    de confundirlo con un 404.
    """
    from app.infrastructure.seed import MATERIAS_SIN_GRUPO

    sembrar(db_session)
    db_session.commit()

    sin_oferta = db_session.execute(
        select(CourseModel.code)
        .where(CourseModel.code.in_(MATERIAS_SIN_GRUPO))
        .where(
            ~select(CourseOfferingModel.id)
            .where(CourseOfferingModel.course_id == CourseModel.id)
            .exists()
        )
    ).scalars()

    assert set(sin_oferta) == set(MATERIAS_SIN_GRUPO)


@pytest.mark.integration
def test_seeded_offerings_all_have_a_schedule(db_session: Session) -> None:
    sembrar(db_session)
    db_session.commit()

    sin_horario = db_session.execute(
        select(func.count())
        .select_from(CourseOfferingModel)
        .where(
            ~select(ScheduleBlockModel.id)
            .where(ScheduleBlockModel.course_offering_id == CourseOfferingModel.id)
            .exists()
        )
    ).scalar_one()

    assert sin_horario == 0


@pytest.mark.integration
def test_seeded_offerings_never_exceed_their_capacity(db_session: Session) -> None:
    # El `CHECK` lo impediría, pero un seed que intente violarlo revienta en la primera
    # ejecución. Se comprueba que la ocupación generada sea siempre válida.
    sembrar(db_session)
    db_session.commit()

    invalidos = db_session.execute(
        select(func.count())
        .select_from(CourseOfferingModel)
        .where(CourseOfferingModel.enrolled_count > CourseOfferingModel.total_capacity)
    ).scalar_one()

    assert invalidos == 0
