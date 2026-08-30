"""Pruebas de integración de los reportes de administración (iteración 4.4).

Aquí lo que se prueba es la aritmética, y la aritmética la hace PostgreSQL: `COUNT`,
`COUNT(DISTINCT ...)`, `GROUP BY` y el orden por ocupación. Un doble en memoria devolvería lo
que el test le dijera devolver, así que no demostraría nada sobre las consultas reales.

El escenario se construye con inscripciones de dos programas distintos, una cancelada y una de
un período cerrado: las tres formas de que un reporte cuente de más si el filtro está mal.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.infrastructure.auth.jwt_auth_service import JWTAuthService
from app.infrastructure.config.settings import get_settings
from app.infrastructure.persistence.sqlalchemy.models.administrator import AdministratorModel
from app.infrastructure.persistence.sqlalchemy.models.course_offering import CourseOfferingModel
from app.infrastructure.persistence.sqlalchemy.models.enrollment import EnrollmentModel
from app.infrastructure.persistence.sqlalchemy.models.program import ProgramModel
from app.infrastructure.persistence.sqlalchemy.models.student import StudentModel
from app.infrastructure.persistence.sqlalchemy.models.user import UserModel
from tests.integration.conftest import CatalogoDePrueba

RUTA_INSCRIPCIONES = "/api/v1/admin/reports/enrollments"
RUTA_OCUPACION = "/api/v1/admin/reports/occupancy"
PASSWORD = "SecurePass123"


@pytest.fixture
def admin(client: TestClient, db_session: Session) -> dict[str, str]:
    """Devuelve la cabecera de autorización de una cuenta con rol ADMIN."""
    hasher = JWTAuthService(get_settings())

    usuario = UserModel(
        id=uuid4(),
        email="admin.reportes@tdea.edu.co",
        password_hash=hasher.hash(PASSWORD),
        role="ADMIN",
        is_active=True,
    )
    db_session.add(usuario)
    db_session.flush()
    db_session.add(
        AdministratorModel(
            id=uuid4(), user_id=usuario.id, full_name="Admin Reportes", department="Registro"
        )
    )
    db_session.commit()

    respuesta = client.post(
        "/api/v1/auth/login", json={"email": usuario.email, "password": PASSWORD}
    )
    assert respuesta.status_code == 200, respuesta.text
    return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}


def _crear_estudiante(db_session: Session, program_id: UUID, sufijo: str) -> UUID:
    """Crea una cuenta con perfil académico y devuelve el identificador del estudiante."""
    hasher = JWTAuthService(get_settings())

    usuario = UserModel(
        id=uuid4(),
        email=f"reporte{sufijo}@tdea.edu.co",
        password_hash=hasher.hash(PASSWORD),
        role="STUDENT",
        is_active=True,
    )
    db_session.add(usuario)
    db_session.flush()

    estudiante = StudentModel(
        id=uuid4(),
        user_id=usuario.id,
        student_code=f"7000{sufijo}",
        program_id=program_id,
        current_semester=3,
        full_name=f"Estudiante Reporte {sufijo}",
        enrollment_date=date(2022, 1, 15),
    )
    db_session.add(estudiante)
    db_session.flush()

    return estudiante.id


@pytest.fixture
def inscripciones(db_session: Session, catalogo: CatalogoDePrueba) -> None:
    """Siembra un escenario con todas las trampas que un reporte puede pisar.

    - Dos estudiantes de Ingeniería de Sistemas y uno de Derecho, para que el desglose por
      programa tenga más de una fila y `unique_students` no coincida con `total_enrollments`.
    - Una inscripción **cancelada**: no debe contar en ninguna cifra.
    - Una inscripción de un período **cerrado**: tampoco, aunque esté activa.
    """
    derecho = ProgramModel(id=uuid4(), code="DERE", name="Derecho", total_semesters=10)
    db_session.add(derecho)
    db_session.flush()

    isis_1 = _crear_estudiante(db_session, catalogo.program_id, "01")
    isis_2 = _crear_estudiante(db_session, catalogo.program_id, "02")
    dere_1 = _crear_estudiante(db_session, derecho.id, "03")

    # El grupo del período cerrado que creó la fixture `catalogo`: se busca por su período,
    # que es el único que no está activo.
    grupo_viejo = (
        db_session.query(CourseOfferingModel)
        .filter(CourseOfferingModel.enrollment_period_id != catalogo.period_id)
        .one()
    )

    # La segunda inscripción de `isis_1` es de OTRA materia, no del otro grupo de la misma.
    # Antes lo era, y ese dato codificaba el fallo que la migración `0014` cerró: una persona no
    # puede cursar la misma materia en dos grupos, porque `academic_history` es único por
    # materia y el cierre del semestre reventaría. Además es el caso realista: quien lleva dos
    # inscripciones lleva dos asignaturas distintas.
    grupo_fisica = CourseOfferingModel(
        id=uuid4(),
        enrollment_period_id=catalogo.period_id,
        course_id=catalogo.fisica_id,
        group_number="01",
        total_capacity=40,
        enrolled_count=0,
    )
    db_session.add(grupo_fisica)
    db_session.flush()

    db_session.add_all(
        [
            # ISIS: dos estudiantes, tres inscripciones activas.
            EnrollmentModel(
                id=uuid4(),
                student_id=isis_1,
                course_offering_id=catalogo.offering_grupo_01_id,
                course_id=catalogo.calculo_i_id,
                enrollment_period_id=catalogo.period_id,
                status="ENROLLED",
            ),
            EnrollmentModel(
                id=uuid4(),
                student_id=isis_1,
                course_offering_id=grupo_fisica.id,
                course_id=catalogo.fisica_id,
                enrollment_period_id=catalogo.period_id,
                status="ENROLLED",
            ),
            EnrollmentModel(
                id=uuid4(),
                student_id=isis_2,
                course_offering_id=catalogo.offering_grupo_01_id,
                course_id=catalogo.calculo_i_id,
                enrollment_period_id=catalogo.period_id,
                status="ENROLLED",
            ),
            # Derecho: una activa.
            EnrollmentModel(
                id=uuid4(),
                student_id=dere_1,
                course_offering_id=catalogo.offering_grupo_01_id,
                course_id=catalogo.calculo_i_id,
                enrollment_period_id=catalogo.period_id,
                status="ENROLLED",
            ),
            # Cancelada: no cuenta.
            EnrollmentModel(
                id=uuid4(),
                student_id=isis_2,
                course_offering_id=catalogo.offering_grupo_02_id,
                course_id=catalogo.calculo_i_id,
                enrollment_period_id=catalogo.period_id,
                status="CANCELLED",
                cancelled_at=datetime.now(UTC),
            ),
            # De un período cerrado: tampoco cuenta, aunque esté activa.
            EnrollmentModel(
                id=uuid4(),
                student_id=isis_2,
                course_offering_id=grupo_viejo.id,
                course_id=grupo_viejo.course_id,
                enrollment_period_id=grupo_viejo.enrollment_period_id,
                status="ENROLLED",
            ),
        ]
    )
    db_session.commit()


# ---------------------------------------------------------------------------
# GET /admin/reports/enrollments
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_el_reporte_cuenta_solo_las_inscripciones_activas_del_periodo_activo(
    client: TestClient, admin: dict[str, str], catalogo: CatalogoDePrueba, inscripciones: None
) -> None:
    respuesta = client.get(RUTA_INSCRIPCIONES, headers=admin)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["period_code"] == "2025-2-V1"
    # Cuatro activas: la cancelada y la del período cerrado quedan fuera.
    assert cuerpo["totals"]["total_enrollments"] == 4
    # Tres personas distintas, aunque una de ellas tenga dos inscripciones.
    assert cuerpo["totals"]["unique_students"] == 3
    # Dos grupos con al menos una inscripción activa.
    assert cuerpo["totals"]["active_offerings"] == 2


@pytest.mark.integration
def test_el_desglose_por_programa_suma_el_total(
    client: TestClient, admin: dict[str, str], inscripciones: None
) -> None:
    """Si los dos números no cuadran, uno de los dos filtros está mal escrito."""
    cuerpo = client.get(RUTA_INSCRIPCIONES, headers=admin).json()

    assert [p["program_code"] for p in cuerpo["by_program"]] == ["ISIS", "DERE"]
    assert sum(p["enrollments"] for p in cuerpo["by_program"]) == (
        cuerpo["totals"]["total_enrollments"]
    )
    isis = cuerpo["by_program"][0]
    assert (isis["enrollments"], isis["students"]) == (3, 2)


@pytest.mark.integration
def test_un_periodo_sin_inscripciones_reporta_ceros(
    client: TestClient, admin: dict[str, str], catalogo: CatalogoDePrueba
) -> None:
    """La ventana está abierta y todavía no ha entrado nadie: cero es la respuesta correcta."""
    cuerpo = client.get(RUTA_INSCRIPCIONES, headers=admin).json()

    assert cuerpo["totals"] == {
        "total_enrollments": 0,
        "unique_students": 0,
        "active_offerings": 0,
    }
    assert cuerpo["by_program"] == []


@pytest.mark.integration
def test_sin_periodo_activo_el_reporte_devuelve_404(
    client: TestClient, admin: dict[str, str]
) -> None:
    respuesta = client.get(RUTA_INSCRIPCIONES, headers=admin)

    assert respuesta.status_code == 404, respuesta.text
    assert respuesta.json()["error"]["code"] == "NO_ACTIVE_PERIOD"


# ---------------------------------------------------------------------------
# GET /admin/reports/occupancy
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_la_ocupacion_llega_ordenada_del_grupo_mas_lleno_al_mas_vacio(
    client: TestClient, admin: dict[str, str], catalogo: CatalogoDePrueba
) -> None:
    """El orden es lo que hace útil la primera página: los grupos a punto de llenarse."""
    respuesta = client.get(RUTA_OCUPACION, headers=admin)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    # Solo los dos grupos del período activo; el del período cerrado no aparece.
    assert cuerpo["total"] == 2
    primero, segundo = cuerpo["offerings"]
    # 37/40 = 92.5 % contra 0/30 = 0 %.
    assert primero["occupancy_rate"] == 92.5
    assert primero["available_slots"] == 3
    assert segundo["occupancy_rate"] == 0.0
    assert primero["course_code"] == "MAT101"


@pytest.mark.integration
def test_la_ocupacion_se_pagina(
    client: TestClient, admin: dict[str, str], catalogo: CatalogoDePrueba
) -> None:
    """Paginado aunque `API.md` no lo pidiera: un período tiene cientos de grupos."""
    respuesta = client.get(RUTA_OCUPACION, params={"page": 2, "size": 1}, headers=admin)

    cuerpo = respuesta.json()
    assert len(cuerpo["offerings"]) == 1
    assert (cuerpo["page"], cuerpo["size"], cuerpo["total"]) == (2, 1, 2)
    assert cuerpo["offerings"][0]["occupancy_rate"] == 0.0


@pytest.mark.integration
def test_la_ocupacion_refleja_el_ajuste_de_cupo_al_instante(
    client: TestClient, admin: dict[str, str], catalogo: CatalogoDePrueba
) -> None:
    """El reporte no se cachea: ampliar el cupo cambia el porcentaje en la siguiente consulta."""
    antes = client.get(RUTA_OCUPACION, headers=admin).json()["offerings"][0]
    assert antes["occupancy_rate"] == 92.5

    ajuste = client.put(
        f"/api/v1/admin/offerings/{catalogo.offering_grupo_01_id}/capacity",
        json={"total_capacity": 74},
        headers=admin,
    )
    assert ajuste.status_code == 200, ajuste.text

    despues = client.get(RUTA_OCUPACION, headers=admin).json()["offerings"][0]
    assert despues["occupancy_rate"] == 50.0


@pytest.mark.integration
def test_sin_periodo_activo_la_ocupacion_devuelve_404(
    client: TestClient, admin: dict[str, str]
) -> None:
    respuesta = client.get(RUTA_OCUPACION, headers=admin)

    assert respuesta.status_code == 404, respuesta.text
    assert respuesta.json()["error"]["code"] == "NO_ACTIVE_PERIOD"


@pytest.mark.integration
def test_un_estudiante_no_puede_ver_los_reportes(
    client: TestClient, estudiante_registrado: dict[str, str]
) -> None:
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": estudiante_registrado["email"],
            "password": estudiante_registrado["password"],
        },
    )
    cabecera = {"Authorization": f"Bearer {login.json()['access_token']}"}

    for ruta in (RUTA_INSCRIPCIONES, RUTA_OCUPACION):
        respuesta = client.get(ruta, headers=cabecera)
        assert respuesta.status_code == 403, respuesta.text
        assert respuesta.json()["error"]["code"] == "ADMIN_REQUIRED"
