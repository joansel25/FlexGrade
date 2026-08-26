"""Pruebas de integración del script de datos de ejemplo.

La idempotencia es lo único que hay que probar aquí a fondo, y solo se puede probar contra
PostgreSQL real: lo que impide los duplicados son las restricciones `UNIQUE` del esquema, y
un doble en memoria no las tiene. Un seed que falla en la segunda ejecución es un seed que
nadie se atreve a ejecutar.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infrastructure.persistence.sqlalchemy.models.academic_history import AcademicHistoryModel
from app.infrastructure.persistence.sqlalchemy.models.administrator import AdministratorModel
from app.infrastructure.persistence.sqlalchemy.models.course import CourseModel
from app.infrastructure.persistence.sqlalchemy.models.course_offering import CourseOfferingModel
from app.infrastructure.persistence.sqlalchemy.models.enrollment_period import EnrollmentPeriodModel
from app.infrastructure.persistence.sqlalchemy.models.professor import ProfessorModel
from app.infrastructure.persistence.sqlalchemy.models.program import ProgramModel
from app.infrastructure.persistence.sqlalchemy.models.program_course import ProgramCourseModel
from app.infrastructure.persistence.sqlalchemy.models.program_course_requirement import (
    ProgramCourseRequirementModel,
)
from app.infrastructure.persistence.sqlalchemy.models.schedule_block import ScheduleBlockModel
from app.infrastructure.persistence.sqlalchemy.models.space import SpaceModel
from app.infrastructure.persistence.sqlalchemy.models.student import StudentModel
from app.infrastructure.persistence.sqlalchemy.models.user import UserModel
from app.infrastructure.seed import CORREO_ADMIN, PASSWORD_DE_EJEMPLO, sembrar

# Volúmenes que fija `docs/DATA_MODEL.md` sección 4.
ESPERADO = {
    ProgramModel: 3,
    ProfessorModel: 10,
    CourseModel: 16,
    CourseOfferingModel: 21,
    SpaceModel: 9,
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
            ProgramCourseRequirementModel,
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


def _requisitos(db_session: Session) -> set[tuple[UUID, UUID, str]]:
    """Devuelve los requisitos sembrados como tríos `(materia, exigida, tipo)`."""
    return {
        (r.course_id, r.required_course_id, r.requirement_type)
        for r in db_session.execute(select(ProgramCourseRequirementModel)).scalars()
    }


def _materias(db_session: Session, *codigos: str) -> dict[str, CourseModel]:
    return {
        c.code: c
        for c in db_session.execute(
            select(CourseModel).where(CourseModel.code.in_(codigos))
        ).scalars()
    }


@pytest.mark.integration
def test_seeded_prerequisite_chain_is_linked(db_session: Session) -> None:
    # MAT101 -> MAT102 -> MAT201: la cadena que la Fase 3 usará para probar la validación de
    # prerrequisitos en más de un nivel.
    sembrar(db_session)
    db_session.commit()

    materias = _materias(db_session, "MAT101", "MAT102", "MAT201")
    enlaces = _requisitos(db_session)

    assert (materias["MAT102"].id, materias["MAT101"].id, "PREREQUISITE") in enlaces
    assert (materias["MAT201"].id, materias["MAT102"].id, "PREREQUISITE") in enlaces


@pytest.mark.integration
def test_seeded_corequisites_cover_the_simple_and_the_mutual_case(
    db_session: Session,
) -> None:
    """Los dos casos que el validador trata distinto tienen datos con los que probarse a mano.

    Sin el par mutuo, el único camino que quedaría sin ejercitar es justo el que resuelve el
    bloqueo circular, que es el más difícil de razonar sobre el papel.
    """
    sembrar(db_session)
    db_session.commit()

    materias = _materias(db_session, "MAT101", "FIS101", "FIS102")
    enlaces = _requisitos(db_session)

    # Simple: Física I exige cursar Cálculo I a la vez, y Cálculo I no exige nada a cambio.
    assert (materias["FIS101"].id, materias["MAT101"].id, "COREQUISITE") in enlaces
    assert (materias["MAT101"].id, materias["FIS101"].id, "COREQUISITE") not in enlaces

    # Mutuo: la teoría y su laboratorio se exigen en las dos direcciones.
    assert (materias["FIS101"].id, materias["FIS102"].id, "COREQUISITE") in enlaces
    assert (materias["FIS102"].id, materias["FIS101"].id, "COREQUISITE") in enlaces


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


@pytest.mark.integration
def test_seed_gives_academic_history_only_to_the_program_that_has_the_chain(
    db_session: Session,
) -> None:
    """El historial sigue al plan de estudios.

    La cadena MAT101 -> MAT102 -> MAT201 pertenece a Ingeniería. Dar Cálculo I a alguien de
    Derecho produciría datos que se contradicen: tendría la materia aprobada y aun así no
    podría inscribir Cálculo II, por no estar en su plan.
    """
    from app.infrastructure.persistence.sqlalchemy.models.program import ProgramModel
    from app.infrastructure.seed import PROGRAMA_CON_CADENA

    sembrar(db_session)
    db_session.commit()

    ingenieria = db_session.execute(
        select(ProgramModel).where(ProgramModel.code == PROGRAMA_CON_CADENA)
    ).scalar_one()

    ajenos = db_session.execute(
        select(func.count())
        .select_from(AcademicHistoryModel)
        .join(StudentModel, StudentModel.id == AcademicHistoryModel.student_id)
        .where(StudentModel.program_id != ingenieria.id)
    ).scalar_one()

    assert ajenos == 0


@pytest.mark.integration
def test_seed_leaves_students_on_both_sides_of_the_prerequisite_rule(
    db_session: Session,
) -> None:
    """Sin este reparto, probar los prerrequisitos a mano exigiría preparar datos antes.

    Tiene que haber a la vez quien pueda inscribir MAT102 y quien no, y quien la tenga
    PERDIDA en vez de aprobada —que es lo que comprueba que la validación distingue ambos
    estados en vez de contar cualquier fila del historial—.
    """
    _recuento, reparto = sembrar(db_session)
    db_session.commit()

    assert reparto["sin_historial"]
    assert reparto["mat101_aprobada"]
    assert reparto["cadena_completa"]
    assert reparto["mat101_perdida"]

    perdidas = db_session.execute(
        select(func.count())
        .select_from(AcademicHistoryModel)
        .where(AcademicHistoryModel.status == "FAILED")
    ).scalar_one()
    assert perdidas > 0


@pytest.mark.integration
def test_todas_las_franjas_sembradas_tienen_aula_de_verdad(db_session: Session) -> None:
    """Ninguna franja queda con un aula que no exista en el inventario.

    Es lo que el texto libre no podía garantizar: antes el aula se generaba al vuelo dentro del
    bucle de grupos y no correspondía a ninguna fila, así que preguntar qué había reservado en
    ella no tenía respuesta.
    """
    sembrar(db_session)
    db_session.commit()

    huerfanas = db_session.execute(
        select(func.count())
        .select_from(ScheduleBlockModel)
        .where(ScheduleBlockModel.space_id.is_(None))
    ).scalar_one()

    assert huerfanas == 0


@pytest.mark.integration
def test_el_inventario_sembrado_cubre_los_tres_tipos_de_espacio(db_session: Session) -> None:
    # Con un solo tipo, la distinción entre aula, laboratorio y auditorio no se ejercitaría
    # nunca y daría igual haberla modelado.
    sembrar(db_session)
    db_session.commit()

    tipos = {s.space_type for s in db_session.execute(select(SpaceModel)).scalars()}

    assert tipos == {"CLASSROOM", "LABORATORY", "AUDITORIUM"}


@pytest.mark.integration
def test_algun_espacio_sembrado_es_mas_pequeno_que_los_grupos_grandes(
    db_session: Session,
) -> None:
    """Sin un aula pequeña, la comprobación de aforo de la 7.2 no tendría caso que rechazar.

    Un juego de datos donde todo cabe deja la regla sin nada contra lo que probarse a mano.
    """
    sembrar(db_session)
    db_session.commit()

    aforos = [s.capacity for s in db_session.execute(select(SpaceModel)).scalars() if s.capacity]

    assert min(aforos) < 40
