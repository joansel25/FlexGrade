"""Pruebas de integración de los endpoints del catálogo.

Recorren las cuatro capas contra PostgreSQL y Redis reales: router -> caso de uso ->
repositorio -> base de datos, con la caché por medio.

El test que da sentido a todo el archivo es
`test_offering_detail_reflects_a_capacity_change_immediately`: demuestra, contra
infraestructura real, que un cambio de cupo se ve al instante aunque el resto del grupo venga
de la caché. Es el criterio de terminado de la Fase 2.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.infrastructure.auth.jwt_auth_service import JWTAuthService
from app.infrastructure.config.settings import get_settings
from app.infrastructure.persistence.sqlalchemy.models.student import StudentModel
from app.infrastructure.persistence.sqlalchemy.models.user import UserModel
from tests.integration.conftest import PASSWORD_DE_PRUEBA, CatalogoDePrueba

RUTA_COURSES = "/api/v1/courses"
RUTA_OFFERINGS = "/api/v1/offerings"
RUTA_PERIODO = "/api/v1/enrollment-periods/current"

# ---------------------------------------------------------------------------
# GET /courses
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_list_courses_returns_the_paginated_envelope(
    client: TestClient, catalogo: CatalogoDePrueba
) -> None:
    respuesta = client.get(RUTA_COURSES)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert set(cuerpo) == {"items", "total", "page", "size"}
    assert cuerpo["total"] == 4


@pytest.mark.integration
def test_list_courses_items_follow_the_documented_shape(
    client: TestClient, catalogo: CatalogoDePrueba
) -> None:
    materia = client.get(RUTA_COURSES).json()["items"][0]

    assert set(materia) == {"id", "code", "name", "credits", "description"}


@pytest.mark.integration
def test_list_courses_filters_by_program(client: TestClient, catalogo: CatalogoDePrueba) -> None:
    cuerpo = client.get(RUTA_COURSES, params={"program_id": str(catalogo.program_id)}).json()

    # Física no está en ningún plan de estudios; el plan de Ingeniería son las dos de Cálculo
    # más el taller.
    assert cuerpo["total"] == 3
    assert str(catalogo.fisica_id) not in {m["id"] for m in cuerpo["items"]}


@pytest.mark.integration
def test_list_courses_filters_by_search_text(
    client: TestClient, catalogo: CatalogoDePrueba
) -> None:
    cuerpo = client.get(RUTA_COURSES, params={"search": "cálculo"}).json()

    assert cuerpo["total"] == 2


@pytest.mark.integration
def test_list_courses_respects_the_page_size(
    client: TestClient, catalogo: CatalogoDePrueba
) -> None:
    cuerpo = client.get(RUTA_COURSES, params={"page": 1, "size": 2}).json()

    assert len(cuerpo["items"]) == 2
    assert cuerpo["total"] == 4


@pytest.mark.integration
def test_list_courses_rejects_a_size_over_the_limit(client: TestClient) -> None:
    # El techo se declara en el router, así que FastAPI lo rechaza antes de llegar al caso de
    # uso: `?size=100000` no puede convertirse en una consulta de cien mil filas.
    assert client.get(RUTA_COURSES, params={"size": 100_000}).status_code == 422


@pytest.mark.integration
def test_list_courses_rejects_a_non_positive_page(client: TestClient) -> None:
    assert client.get(RUTA_COURSES, params={"page": 0}).status_code == 422


# ---------------------------------------------------------------------------
# GET /courses/{id}
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_course_detail_includes_its_requirements_for_the_requested_program(
    client: TestClient, catalogo: CatalogoDePrueba
) -> None:
    cuerpo = client.get(
        f"{RUTA_COURSES}/{catalogo.calculo_ii_id}",
        params={"program_id": str(catalogo.program_id)},
    ).json()

    assert cuerpo["code"] == "MAT102"
    assert cuerpo["program_id"] == str(catalogo.program_id)
    assert [p["code"] for p in cuerpo["prerequisites"]] == ["MAT101"]
    assert cuerpo["corequisites"] == []


@pytest.mark.integration
def test_course_detail_requirements_change_with_the_program(
    client: TestClient, catalogo: CatalogoDePrueba
) -> None:
    """La misma materia, otro plan, otra respuesta.

    En Administración, Cálculo II está en el plan y no exige nada. Es la afirmación que la
    tabla anterior no podía sostener a la vez que la de Ingeniería.
    """
    cuerpo = client.get(
        f"{RUTA_COURSES}/{catalogo.calculo_ii_id}",
        params={"program_id": str(catalogo.otro_program_id)},
    ).json()

    assert cuerpo["prerequisites"] == []


@pytest.mark.integration
def test_course_detail_without_a_program_returns_no_requirements(
    client: TestClient, catalogo: CatalogoDePrueba
) -> None:
    cuerpo = client.get(f"{RUTA_COURSES}/{catalogo.calculo_ii_id}").json()

    assert cuerpo["program_id"] is None
    assert cuerpo["prerequisites"] == []
    assert cuerpo["corequisites"] == []


@pytest.mark.integration
def test_course_detail_includes_the_mutual_corequisite(
    client: TestClient, catalogo: CatalogoDePrueba
) -> None:
    cuerpo = client.get(
        f"{RUTA_COURSES}/{catalogo.calculo_i_id}",
        params={"program_id": str(catalogo.program_id)},
    ).json()

    assert cuerpo["prerequisites"] == []
    assert [c["code"] for c in cuerpo["corequisites"]] == ["TAL101"]


@pytest.mark.integration
def test_course_detail_when_missing_returns_404_with_the_error_code(client: TestClient) -> None:
    respuesta = client.get(f"{RUTA_COURSES}/{uuid4()}")

    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["code"] == "COURSE_NOT_FOUND"


# ---------------------------------------------------------------------------
# GET /courses/{id}/offerings
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_course_offerings_returns_only_the_active_period(
    client: TestClient, catalogo: CatalogoDePrueba
) -> None:
    # La fixture crea un tercer grupo de la misma materia en un período cerrado.
    cuerpo = client.get(f"{RUTA_COURSES}/{catalogo.calculo_i_id}/offerings").json()

    assert cuerpo["period_code"] == "2025-2-V1"
    assert [g["group_number"] for g in cuerpo["offerings"]] == ["01", "02"]


@pytest.mark.integration
def test_course_offerings_include_professor_schedule_and_slots(
    client: TestClient, catalogo: CatalogoDePrueba
) -> None:
    cuerpo = client.get(f"{RUTA_COURSES}/{catalogo.calculo_i_id}/offerings").json()
    grupo_01 = next(g for g in cuerpo["offerings"] if g["group_number"] == "01")

    assert grupo_01["professor"] == "Ana Pérez"
    assert grupo_01["available_slots"] == 3
    assert [f["day_of_week"] for f in grupo_01["schedule"]] == [1, 3]


@pytest.mark.integration
def test_course_offerings_include_a_group_without_professor(
    client: TestClient, catalogo: CatalogoDePrueba
) -> None:
    cuerpo = client.get(f"{RUTA_COURSES}/{catalogo.calculo_i_id}/offerings").json()
    grupo_02 = next(g for g in cuerpo["offerings"] if g["group_number"] == "02")

    assert grupo_02["professor"] is None
    assert grupo_02["schedule"] == []


@pytest.mark.integration
def test_course_offerings_when_not_offered_returns_an_empty_list(
    client: TestClient, catalogo: CatalogoDePrueba
) -> None:
    cuerpo = client.get(f"{RUTA_COURSES}/{catalogo.fisica_id}/offerings").json()

    assert cuerpo["offerings"] == []


@pytest.mark.integration
def test_course_offerings_when_no_active_period_returns_404(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    db_session.execute(text("UPDATE enrollment_periods SET is_active = FALSE"))
    db_session.commit()

    respuesta = client.get(f"{RUTA_COURSES}/{catalogo.calculo_i_id}/offerings")

    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["code"] == "NO_ACTIVE_PERIOD"


# ---------------------------------------------------------------------------
# GET /offerings/{id} — la regla crítica
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_offering_detail_returns_the_group(client: TestClient, catalogo: CatalogoDePrueba) -> None:
    cuerpo = client.get(f"{RUTA_OFFERINGS}/{catalogo.offering_grupo_01_id}").json()

    assert cuerpo["group_number"] == "01"
    assert cuerpo["professor"] == "Ana Pérez"
    assert cuerpo["available_slots"] == 3
    assert cuerpo["course_id"] == str(catalogo.calculo_i_id)


@pytest.mark.integration
def test_offering_detail_reflects_a_capacity_change_immediately(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    """El criterio de terminado de la Fase 2, contra Redis y PostgreSQL reales.

    Se consulta el grupo —lo que lo deja cacheado—, se ocupan dos cupos por debajo, y se
    vuelve a consultar dentro de la ventana del TTL de 30 segundos. La respuesta tiene que
    mostrar el cupo nuevo.

    Si este test falla, significa que la disponibilidad se está sirviendo desde la caché, y
    entonces el sistema puede decirle a un estudiante que hay plaza cuando ya no la hay: el
    fallo exacto que el proyecto entero existe para evitar.
    """
    ruta = f"{RUTA_OFFERINGS}/{catalogo.offering_grupo_01_id}"

    primera = client.get(ruta).json()
    assert primera["available_slots"] == 3

    db_session.execute(
        text(
            "UPDATE course_offerings SET enrolled_count = 39, version = version + 1 "
            "WHERE id = :id"
        ),
        {"id": catalogo.offering_grupo_01_id},
    )
    db_session.commit()

    segunda = client.get(ruta).json()

    assert segunda["available_slots"] == 1, "la disponibilidad se sirvió desde la caché"
    assert segunda["enrolled_count"] == 39
    # La parte estática sí se sirve cacheada, y sigue siendo correcta.
    assert segunda["professor"] == "Ana Pérez"
    assert len(segunda["schedule"]) == 2


@pytest.mark.integration
def test_offering_detail_shows_zero_slots_when_the_group_fills_up(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    ruta = f"{RUTA_OFFERINGS}/{catalogo.offering_grupo_01_id}"
    client.get(ruta)

    db_session.execute(
        text("UPDATE course_offerings SET enrolled_count = 40 WHERE id = :id"),
        {"id": catalogo.offering_grupo_01_id},
    )
    db_session.commit()

    assert client.get(ruta).json()["available_slots"] == 0


@pytest.mark.integration
def test_offering_detail_when_missing_returns_404_with_the_error_code(
    client: TestClient,
) -> None:
    respuesta = client.get(f"{RUTA_OFFERINGS}/{uuid4()}")

    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["code"] == "OFFERING_NOT_FOUND"


# ---------------------------------------------------------------------------
# GET /enrollment-periods/current
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_current_period_returns_the_active_window_as_open(
    client: TestClient, catalogo: CatalogoDePrueba
) -> None:
    cuerpo = client.get(RUTA_PERIODO).json()

    assert cuerpo["code"] == "2025-2-V1"
    assert cuerpo["is_active"] is True
    assert cuerpo["is_open"] is True
    assert cuerpo["time_remaining_seconds"] > 0


@pytest.mark.integration
def test_current_period_when_activated_but_not_started_is_not_open(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    # La distinción que el frontend necesita: hay período, pero todavía no abre.
    db_session.execute(
        text(
            "UPDATE enrollment_periods "
            "SET starts_at = NOW() + INTERVAL '2 days', ends_at = NOW() + INTERVAL '4 days' "
            "WHERE is_active = TRUE"
        )
    )
    db_session.commit()

    cuerpo = client.get(RUTA_PERIODO).json()

    assert cuerpo["is_active"] is True
    assert cuerpo["is_open"] is False


@pytest.mark.integration
def test_current_period_when_none_is_active_returns_404(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    db_session.execute(text("UPDATE enrollment_periods SET is_active = FALSE"))
    db_session.commit()

    respuesta = client.get(RUTA_PERIODO)

    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["code"] == "NO_ACTIVE_PERIOD"


# ---------------------------------------------------------------------------
# GET /students/me/study-plan  (iteración 6.1)
# ---------------------------------------------------------------------------


def _cabecera_de_estudiante(
    client: TestClient,
    db_session: Session,
    catalogo: CatalogoDePrueba,
    codigo: str,
    correo: str,
) -> dict[str, str]:
    """Crea una cuenta con perfil académico en el programa de la fixture y la autentica."""
    hasher = JWTAuthService(get_settings())
    usuario = UserModel(
        id=uuid4(),
        email=f"{correo}@tdea.edu.co",
        password_hash=hasher.hash(PASSWORD_DE_PRUEBA),
        role="STUDENT",
        is_active=True,
    )
    db_session.add(usuario)
    db_session.flush()
    db_session.add(
        StudentModel(
            id=uuid4(),
            user_id=usuario.id,
            student_code=codigo,
            program_id=catalogo.program_id,
            current_semester=2,
            full_name=f"Estudiante {codigo}",
            enrollment_date=date(2022, 1, 15),
        )
    )
    db_session.commit()

    login = client.post(
        "/api/v1/auth/login", json={"email": usuario.email, "password": PASSWORD_DE_PRUEBA}
    )
    assert login.status_code == 200, login.text

    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.integration
def test_el_plan_de_estudios_trae_el_semestre_y_la_obligatoriedad(
    client: TestClient, db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    """Son los dos datos que la entidad `Course` no tiene, porque no son suyos.

    Viven en `program_courses`, la relación entre el programa y la materia, y solo este
    endpoint los expone.
    """
    hasher = JWTAuthService(get_settings())
    usuario = UserModel(
        id=uuid4(),
        email="plan.estudios@tdea.edu.co",
        password_hash=hasher.hash(PASSWORD_DE_PRUEBA),
        role="STUDENT",
        is_active=True,
    )
    db_session.add(usuario)
    db_session.flush()
    db_session.add(
        StudentModel(
            id=uuid4(),
            user_id=usuario.id,
            student_code="8800001",
            program_id=catalogo.program_id,
            current_semester=2,
            full_name="Estudiante Plan",
            enrollment_date=date(2022, 1, 15),
        )
    )
    db_session.commit()

    login = client.post(
        "/api/v1/auth/login", json={"email": usuario.email, "password": PASSWORD_DE_PRUEBA}
    )
    assert login.status_code == 200, login.text
    cabecera = {"Authorization": f"Bearer {login.json()['access_token']}"}

    respuesta = client.get("/api/v1/students/me/study-plan", headers=cabecera)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["program_code"] == "ISIS"

    codigos = [c["code"] for c in cuerpo["courses"]]
    # La fixture `catalogo` pone en el plan las dos de Cálculo y el taller, ordenados por
    # semestre; Física queda FUERA a propósito, y es justo lo que este endpoint no debe
    # devolver.
    assert codigos == ["MAT101", "MAT102", "TAL101"]
    assert "FIS101" not in codigos

    calculo_i = cuerpo["courses"][0]
    assert calculo_i["suggested_semester"] == 1
    assert calculo_i["is_mandatory"] is True
    # Los créditos se suman en el servidor: 4 + 4 + 1.
    assert cuerpo["total_credits"] == 9


@pytest.mark.integration
def test_el_plan_de_estudios_exige_sesion(client: TestClient) -> None:
    """El programa sale del token: sin él no hay plan que devolver."""
    respuesta = client.get("/api/v1/students/me/study-plan")

    assert respuesta.status_code == 401, respuesta.text


@pytest.mark.integration
def test_el_plan_semaforiza_cada_materia_contra_el_estado_real(
    client: TestClient, db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    """Tres estados distintos en una sola respuesta, calculados contra PostgreSQL real.

    Es donde se comprueba lo que los dobles no pueden: que las consultas que alimentan al
    semáforo —requisitos por plan, historial aprobado, oferta del período— traen lo que deben.
    Un resolutor impecable alimentado por un `WHERE` equivocado pinta el plan al revés.
    """
    cabecera = _cabecera_de_estudiante(client, db_session, catalogo, "8800002", "semaforo")

    cuerpo = client.get("/api/v1/students/me/study-plan", headers=cabecera).json()
    estados = {c["code"]: c["status"] for c in cuerpo["courses"]}
    por_codigo = {c["code"]: c for c in cuerpo["courses"]}

    # MAT101 no exige aprobar nada y tiene dos grupos abiertos.
    assert estados["MAT101"] == "AVAILABLE"
    # MAT102 exige aprobar MAT101, que este estudiante no ha cursado.
    assert estados["MAT102"] == "BLOCKED"
    assert por_codigo["MAT102"]["missing_prerequisites"] == ["MAT101"]
    # El taller cumple requisitos —es correquisito MUTUO de MAT101, y por tanto exento— pero
    # la fixture no le abre ningún grupo: ofrecer inscribirlo llevaría a una pantalla vacía.
    assert estados["TAL101"] == "NOT_OFFERED"


@pytest.mark.integration
def test_una_materia_aprobada_cuenta_como_avance_del_plan(
    client: TestClient, db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    """`approved_credits` responde «cuánto llevo», y desbloquea lo que dependía de ella."""
    cabecera = _cabecera_de_estudiante(client, db_session, catalogo, "8800003", "aprobada")
    estudiante_id = db_session.execute(
        text("SELECT id FROM students WHERE student_code = '8800003'")
    ).scalar_one()
    db_session.execute(
        text(
            "INSERT INTO academic_history "
            "(student_id, course_id, academic_period, status, final_grade) "
            "VALUES (:s, :c, '2025-1', 'APPROVED', 4.2)"
        ),
        {"s": estudiante_id, "c": catalogo.calculo_i_id},
    )
    db_session.commit()

    cuerpo = client.get("/api/v1/students/me/study-plan", headers=cabecera).json()
    estados = {c["code"]: c["status"] for c in cuerpo["courses"]}

    assert estados["MAT101"] == "APPROVED"
    # Y con ella aprobada, Cálculo II deja de estar bloqueada.
    assert estados["MAT102"] == "NOT_OFFERED"
    assert cuerpo["approved_credits"] == 4


@pytest.mark.integration
def test_una_materia_inscrita_se_distingue_de_una_disponible(
    client: TestClient, db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    # Sin este estado, la materia que la persona ya está cursando aparecería como «disponible»
    # y la pantalla la invitaría a inscribir algo que ya tiene.
    cabecera = _cabecera_de_estudiante(client, db_session, catalogo, "8800004", "inscrita")
    inscripcion = client.post(
        "/api/v1/enrollments",
        json={"course_offering_id": str(catalogo.offering_grupo_02_id)},
        headers=cabecera,
    )
    assert inscripcion.status_code == 201, inscripcion.text

    cuerpo = client.get("/api/v1/students/me/study-plan", headers=cabecera).json()

    assert {c["code"]: c["status"] for c in cuerpo["courses"]}["MAT101"] == "ENROLLED"
