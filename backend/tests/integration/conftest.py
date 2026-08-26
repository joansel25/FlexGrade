"""Fixtures de los tests de integración.

Se ejecutan contra el PostgreSQL real de `docker-compose` (o el servicio del
runner en CI), no contra SQLite: el esquema usa `gen_random_uuid()`, CHECK
constraints, índices parciales y un trigger de `updated_at`, y ninguno de esos
elementos existe en SQLite. Probar contra un motor distinto daría un verde falso.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from urllib.parse import urlparse, urlunparse
from uuid import UUID, uuid4

import psycopg
import pytest
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.infrastructure.auth.jwt_auth_service import JWTAuthService
from app.infrastructure.cache.client import get_redis_client
from app.infrastructure.config.settings import get_settings
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
from app.infrastructure.persistence.sqlalchemy.session import get_session_factory

PASSWORD_DE_PRUEBA = "SecurePass123"

# Orden de limpieza: SIEMPRE de hija a padre, para no violar las claves foráneas. Cada tabla
# nueva del esquema tiene que aparecer aquí, y antes que aquellas a las que referencia; una
# tabla olvidada deja filas que hacen fallar al test siguiente por una restricción UNIQUE.
# No se toca `alembic_version`: perder el historial de migraciones dejaría la base inservible.
TABLAS_A_LIMPIAR: tuple[str, ...] = (
    "enrollments",
    "academic_history",
    "schedule_blocks",
    "course_offerings",
    "spaces",
    "program_course_requirements",
    "program_courses",
    "courses",
    "professors",
    "enrollment_periods",
    "students",
    "administrators",
    "users",
    "programs",
)


@pytest.fixture(scope="session", autouse=True)
def base_de_datos_de_pruebas() -> None:
    """Prepara la base de datos antes de que corra ningún test de integración.

    La crea si falta y le aplica todas las migraciones. Vive AQUÍ y no en el conftest raíz por
    una razón que el CI dejó clara: como fixture global se ejecutaba también para los tests
    unitarios, que deben poder correr sin PostgreSQL levantado. En el paso de unitarios del CI
    no hay ninguna base alcanzable —y no debe haberla—, así que los 168 tests unitarios
    fallaban con un error de resolución de nombre antes siquiera de empezar.

    Usar Alembic y no un `create_all` significa que los tests corren contra exactamente el
    mismo esquema que DEV, STAGING y PROD, con sus triggers, índices parciales y `CHECK`.
    """
    from alembic import command
    from alembic.config import Config

    url = os.environ["DATABASE_URL"]
    _crear_base_si_falta(url)

    configuracion = Config("alembic.ini")
    command.upgrade(configuracion, "head")


def _crear_base_si_falta(url: str) -> None:
    """Crea la base de datos de pruebas si todavía no existe.

    `CREATE DATABASE` no admite ejecutarse dentro de una transacción, de ahí el `autocommit`.
    Se conecta a `postgres`, la base de mantenimiento que siempre está presente.
    """
    partes = urlparse(url)
    objetivo = partes.path.lstrip("/")
    # `psycopg.connect` no entiende el prefijo de dialecto de SQLAlchemy.
    mantenimiento = urlunparse(partes._replace(scheme="postgresql", path="/postgres"))

    with psycopg.connect(mantenimiento, autocommit=True) as conexion:
        existe = conexion.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (objetivo,)
        ).fetchone()

        if existe is None:
            conexion.execute(f'CREATE DATABASE "{objetivo}"')


@pytest.fixture(autouse=True)
def cache_limpia() -> Iterator[None]:
    """Vacía la caché del catálogo antes y después de cada test de integración.

    Es `autouse` a propósito. Redis es un servicio real y compartido: una entrada que deje un
    test sobrevive al siguiente, y el resultado sería una suite que pasa o falla según el
    orden de ejecución —el tipo de fallo intermitente que cuesta días localizar—. Solo se
    borran las claves del catálogo, nunca la base entera, para no pisar nada más que corra
    contra el mismo Redis.
    """
    _vaciar_cache_del_catalogo()
    yield
    _vaciar_cache_del_catalogo()


def _vaciar_cache_del_catalogo() -> None:
    cliente = get_redis_client()
    try:
        claves = list(cliente.scan_iter(match="catalog:*"))
        if claves:
            cliente.delete(*claves)
    except RedisError:
        # Si Redis no está disponible, los casos de uso degradan y van a PostgreSQL: los
        # tests siguen siendo válidos, solo dejan de ejercitar el camino de la caché.
        pass


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Sesión contra la base de datos real.

    Al terminar borra las filas creadas por el test, en orden hijo -> padre para respetar las
    claves foráneas.
    """
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.rollback()
        for tabla in TABLAS_A_LIMPIAR:
            session.execute(text(f"DELETE FROM {tabla}"))
        session.commit()
        session.close()


@pytest.fixture
def estudiante_registrado(db_session: Session) -> dict[str, str]:
    """Crea en la base de datos un programa, una cuenta y su perfil académico.

    Returns:
        El correo y el código del estudiante creado.
    """
    settings = get_settings()
    hasher = JWTAuthService(settings)

    programa = ProgramModel(
        id=uuid4(),
        code=f"ISIS{uuid4().hex[:4]}",
        name="Ingeniería de Sistemas",
        total_semesters=10,
    )
    usuario = UserModel(
        id=uuid4(),
        email="estudiante.integracion@tdea.edu.co",
        password_hash=hasher.hash(PASSWORD_DE_PRUEBA),
        role="STUDENT",
        is_active=True,
    )
    estudiante = StudentModel(
        id=uuid4(),
        user_id=usuario.id,
        student_code="9876543",
        program_id=programa.id,
        current_semester=6,
        full_name="Estudiante De Integración",
        enrollment_date=date(2022, 1, 15),
    )

    # Se insertan en orden padre -> hijo con un flush entre medias. Los modelos
    # no declaran `relationship()`, así que SQLAlchemy no puede deducir el orden
    # por sí solo y `students` llegaría antes que `users`, violando la FK.
    db_session.add(programa)
    db_session.add(usuario)
    db_session.flush()
    db_session.add(estudiante)
    db_session.commit()

    return {
        "email": usuario.email,
        "password": PASSWORD_DE_PRUEBA,
        "student_code": estudiante.student_code,
        "program_code": programa.code,
        "program_name": programa.name,
    }


@dataclass(frozen=True)
class CatalogoDePrueba:
    """Identificadores del catálogo que crea la fixture `catalogo`.

    Se devuelven en una estructura tipada y no en un diccionario para que un error de nombre
    lo detecte `mypy` y no una `KeyError` a mitad del test.
    """

    program_id: UUID
    #: Segundo programa, con SU PROPIO plan. Existe para que los tests puedan comprobar que un
    #: requisito declarado en una carrera no rige en la otra, que es la razón de ser de la
    #: iteración 6.2. Comparte `calculo_i` y `calculo_ii` con el primero.
    otro_program_id: UUID
    period_id: UUID
    professor_id: UUID
    calculo_i_id: UUID
    calculo_ii_id: UUID
    fisica_id: UUID
    #: Taller de Matemáticas. Con `calculo_i_id` forman el par de correquisitos MUTUOS.
    taller_id: UUID
    offering_grupo_01_id: UUID
    offering_grupo_02_id: UUID


@pytest.fixture
def catalogo(db_session: Session) -> CatalogoDePrueba:
    """Crea un catálogo pequeño pero completo, con todas las relaciones cableadas.

    Contiene lo justo para ejercitar cada camino de los repositorios: cuatro materias, dos
    planes de estudio que comparten dos de ellas, un
    plan de estudios que deja fuera una de ellas (para comprobar que el filtro por programa la
    excluye de verdad), un período activo, dos grupos —uno con docente y horario, otro sin
    docente ni horario— y un grupo de un período inactivo que nunca debe aparecer en las
    consultas del período vigente.

    Los requisitos cubren los tres casos que la iteración 6.2 distingue:

    - `MAT102` exige `MAT101` como PRERREQUISITO en el plan de Ingeniería.
    - `MAT101` y `TAL101` se exigen MUTUAMENTE como correquisitos —la asignatura y su taller,
      que se cursan juntos—, que es el par capaz de producir un bloqueo circular.
    - `ADMI` incluye las mismas `MAT101` y `MAT102` SIN ningún requisito entre ellas. Es la
      comprobación que da sentido a toda la iteración: el mismo par de materias, dos planes,
      dos reglas distintas. Con la tabla anterior esas dos verdades no cabían a la vez.

    `FIS101` sigue fuera de TODOS los planes, como antes de la 6.2: es lo que comprueba que el
    catálogo completo no se une a `program_courses` y no la hace desaparecer.
    """
    # Códigos fijos y reconocibles, no generados: `db_session` vacía todas las tablas del
    # catálogo al terminar cada test, así que no hay riesgo de colisión entre ejecuciones y
    # las aserciones pueden hablar de "MAT101" en vez de una cadena impredecible.
    programa = ProgramModel(
        id=uuid4(), code="ISIS", name="Ingeniería de Sistemas", total_semesters=10
    )
    otro_programa = ProgramModel(
        id=uuid4(), code="ADMI", name="Administración de Empresas", total_semesters=8
    )
    profesor = ProfessorModel(id=uuid4(), full_name="Ana Pérez", email="ana.perez@tdea.edu.co")

    calculo_i = CourseModel(
        id=uuid4(), code="MAT101", name="Cálculo I", credits=4, description="Diferencial"
    )
    calculo_ii = CourseModel(
        id=uuid4(), code="MAT102", name="Cálculo II", credits=4, description="Integral"
    )
    fisica = CourseModel(id=uuid4(), code="FIS101", name="Física", credits=3)
    # El nombre evita a propósito la palabra «Cálculo» y su semestre sugerido es el 4: así no
    # se cuela en las búsquedas por texto ni en los filtros por semestre de los otros tests,
    # que hablan de las dos materias de Cálculo.
    taller = CourseModel(id=uuid4(), code="TAL101", name="Taller de Matemáticas", credits=1)

    activo = EnrollmentPeriodModel(
        id=uuid4(),
        code="2025-2-V1",
        academic_period="2025-2",
        name="Matrícula 2025-2",
        starts_at=datetime.now(UTC) - timedelta(days=1),
        ends_at=datetime.now(UTC) + timedelta(days=1),
        is_active=True,
    )
    inactivo = EnrollmentPeriodModel(
        id=uuid4(),
        code="2025-1-V1",
        academic_period="2025-1",
        name="Matrícula 2025-1",
        starts_at=datetime.now(UTC) - timedelta(days=200),
        ends_at=datetime.now(UTC) - timedelta(days=190),
        is_active=False,
    )

    db_session.add_all(
        [
            programa,
            otro_programa,
            profesor,
            calculo_i,
            calculo_ii,
            fisica,
            taller,
            activo,
            inactivo,
        ]
    )
    db_session.flush()

    # Plan de Ingeniería: Cálculo I en 1.º, Cálculo II en 2.º y el par Física/Laboratorio en
    # 2.º. El plan de Administración repite las dos de Cálculo y nada más.
    db_session.add_all(
        [
            ProgramCourseModel(
                program_id=programa.id, course_id=calculo_i.id, suggested_semester=1
            ),
            ProgramCourseModel(
                program_id=programa.id, course_id=calculo_ii.id, suggested_semester=2
            ),
            ProgramCourseModel(program_id=programa.id, course_id=taller.id, suggested_semester=4),
            ProgramCourseModel(
                program_id=otro_programa.id, course_id=calculo_i.id, suggested_semester=1
            ),
            ProgramCourseModel(
                program_id=otro_programa.id, course_id=calculo_ii.id, suggested_semester=3
            ),
        ]
    )
    # Los requisitos van DESPUÉS de los planes, y no por orden estético: sus claves foráneas
    # son compuestas contra `program_courses`, así que una materia que no esté ya en el plan
    # hace fallar la inserción.
    db_session.flush()
    db_session.add_all(
        [
            ProgramCourseRequirementModel(
                program_id=programa.id,
                course_id=calculo_ii.id,
                required_course_id=calculo_i.id,
                requirement_type="PREREQUISITE",
            ),
            ProgramCourseRequirementModel(
                program_id=programa.id,
                course_id=calculo_i.id,
                required_course_id=taller.id,
                requirement_type="COREQUISITE",
            ),
            ProgramCourseRequirementModel(
                program_id=programa.id,
                course_id=taller.id,
                required_course_id=calculo_i.id,
                requirement_type="COREQUISITE",
            ),
        ]
    )

    grupo_01 = CourseOfferingModel(
        id=uuid4(),
        enrollment_period_id=activo.id,
        course_id=calculo_i.id,
        professor_id=profesor.id,
        group_number="01",
        total_capacity=40,
        enrolled_count=37,
    )
    # Sin docente y sin horario: comprueba que el repositorio no lo hace desaparecer.
    grupo_02 = CourseOfferingModel(
        id=uuid4(),
        enrollment_period_id=activo.id,
        course_id=calculo_i.id,
        group_number="02",
        total_capacity=30,
        enrolled_count=0,
    )
    # De un período cerrado: nunca debe salir en las consultas del período activo.
    grupo_viejo = CourseOfferingModel(
        id=uuid4(),
        enrollment_period_id=inactivo.id,
        course_id=calculo_i.id,
        group_number="09",
        total_capacity=30,
        enrolled_count=30,
    )
    db_session.add_all([grupo_01, grupo_02, grupo_viejo])

    # Inventario mínimo de espacios. `A-201` y `A-203` los usan las franjas de abajo; `B-101` y
    # `B-102` existen para que los tests que abren un grupo por la API tengan aulas que indicar
    # sin inventarlas.
    espacios = {
        codigo: SpaceModel(
            id=uuid4(), code=codigo, space_type="CLASSROOM", capacity=aforo, campus="Sede"
        )
        for codigo, aforo in (("A-201", 40), ("A-203", 35), ("B-101", 50), ("B-102", 30))
    }
    db_session.add_all(list(espacios.values()))
    db_session.flush()

    db_session.add_all(
        [
            ScheduleBlockModel(
                course_offering_id=grupo_01.id,
                day_of_week=3,
                start_time=time(8, 0),
                end_time=time(10, 0),
                space_id=espacios["A-203"].id,
            ),
            ScheduleBlockModel(
                course_offering_id=grupo_01.id,
                day_of_week=1,
                start_time=time(8, 0),
                end_time=time(10, 0),
                space_id=espacios["A-201"].id,
            ),
        ]
    )
    db_session.commit()

    return CatalogoDePrueba(
        program_id=programa.id,
        otro_program_id=otro_programa.id,
        period_id=activo.id,
        professor_id=profesor.id,
        calculo_i_id=calculo_i.id,
        calculo_ii_id=calculo_ii.id,
        fisica_id=fisica.id,
        taller_id=taller.id,
        offering_grupo_01_id=grupo_01.id,
        offering_grupo_02_id=grupo_02.id,
    )
