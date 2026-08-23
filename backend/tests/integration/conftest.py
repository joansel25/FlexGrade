"""Fixtures de los tests de integración.

Se ejecutan contra el PostgreSQL real de `docker-compose` (o el servicio del
runner en CI), no contra SQLite: el esquema usa `gen_random_uuid()`, CHECK
constraints, índices parciales y un trigger de `updated_at`, y ninguno de esos
elementos existe en SQLite. Probar contra un motor distinto daría un verde falso.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.infrastructure.auth.jwt_auth_service import JWTAuthService
from app.infrastructure.config.settings import get_settings
from app.infrastructure.persistence.sqlalchemy.models.program import ProgramModel
from app.infrastructure.persistence.sqlalchemy.models.student import StudentModel
from app.infrastructure.persistence.sqlalchemy.models.user import UserModel
from app.infrastructure.persistence.sqlalchemy.session import get_session_factory

PASSWORD_DE_PRUEBA = "SecurePass123"


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Sesión contra la base de datos real.

    Al terminar borra las filas creadas por el test. Se limpia por tabla en
    orden hijo -> padre para respetar las claves foráneas, y no se hace TRUNCATE
    de `alembic_version` para no perder el historial de migraciones.
    """
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.rollback()
        session.execute(text("DELETE FROM students"))
        session.execute(text("DELETE FROM administrators"))
        session.execute(text("DELETE FROM users"))
        session.execute(text("DELETE FROM programs"))
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
    }
