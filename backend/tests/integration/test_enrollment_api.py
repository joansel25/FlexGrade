"""Pruebas de integración de los endpoints de inscripción y del horario.

Recorren las cuatro capas contra PostgreSQL real, y con token de verdad: router → guard →
caso de uso → repositorio → base de datos. Es el nivel donde se comprueba que la autorización
está puesta —que nadie inscribe ni cancela en nombre de otro— y que los códigos de error son
los que `API.md` promete.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.infrastructure.auth.jwt_auth_service import JWTAuthService
from app.infrastructure.config.settings import get_settings
from app.infrastructure.persistence.sqlalchemy.models.student import StudentModel
from app.infrastructure.persistence.sqlalchemy.models.user import UserModel
from tests.integration.conftest import CatalogoDePrueba

RUTA_ENROLLMENTS = "/api/v1/enrollments"
RUTA_HORARIO = "/api/v1/students/me/schedule"
PASSWORD = "SecurePass123"


def _crear_cuenta(db_session: Session, program_id: UUID, sufijo: str = "01") -> dict[str, str]:
    """Crea una cuenta con perfil académico y devuelve sus credenciales."""
    hasher = JWTAuthService(get_settings())

    usuario = UserModel(
        id=uuid4(),
        email=f"inscripcion{sufijo}@tdea.edu.co",
        password_hash=hasher.hash(PASSWORD),
        role="STUDENT",
        is_active=True,
    )
    db_session.add(usuario)
    db_session.flush()

    estudiante = StudentModel(
        id=uuid4(),
        user_id=usuario.id,
        student_code=f"60000{sufijo}",
        program_id=program_id,
        current_semester=3,
        full_name=f"Estudiante API {sufijo}",
        enrollment_date=date(2022, 1, 15),
    )
    db_session.add(estudiante)
    db_session.commit()

    return {"email": usuario.email, "password": PASSWORD}


def _token(client: TestClient, credenciales: dict[str, str]) -> str:
    respuesta = client.post("/api/v1/auth/login", json=credenciales)
    assert respuesta.status_code == 200, respuesta.text
    return str(respuesta.json()["access_token"])


def _cabecera(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# POST /enrollments
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_enroll_returns_201_with_the_documented_body(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    token = _token(client, _crear_cuenta(db_session, catalogo.program_id))

    respuesta = client.post(
        RUTA_ENROLLMENTS,
        json={"course_offering_id": str(catalogo.offering_grupo_01_id)},
        headers=_cabecera(token),
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["course_code"] == "MAT101"
    assert cuerpo["course_name"] == "Cálculo I"
    assert cuerpo["group_number"] == "01"
    assert cuerpo["status"] == "ENROLLED"
    assert cuerpo["enrolled_at"] is not None


@pytest.mark.integration
def test_enroll_discounts_the_seat_in_the_database(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    token = _token(client, _crear_cuenta(db_session, catalogo.program_id))
    antes = db_session.execute(
        text("SELECT enrolled_count FROM course_offerings WHERE id = :i"),
        {"i": catalogo.offering_grupo_01_id},
    ).scalar_one()

    client.post(
        RUTA_ENROLLMENTS,
        json={"course_offering_id": str(catalogo.offering_grupo_01_id)},
        headers=_cabecera(token),
    )

    despues = db_session.execute(
        text("SELECT enrolled_count FROM course_offerings WHERE id = :i"),
        {"i": catalogo.offering_grupo_01_id},
    ).scalar_one()
    assert despues == antes + 1


@pytest.mark.integration
def test_enroll_without_a_token_is_rejected(client: TestClient, catalogo: CatalogoDePrueba) -> None:
    respuesta = client.post(
        RUTA_ENROLLMENTS, json={"course_offering_id": str(catalogo.offering_grupo_01_id)}
    )

    assert respuesta.status_code == 401


@pytest.mark.integration
def test_enroll_twice_in_the_same_group_returns_409(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    token = _token(client, _crear_cuenta(db_session, catalogo.program_id))
    cuerpo = {"course_offering_id": str(catalogo.offering_grupo_01_id)}
    client.post(RUTA_ENROLLMENTS, json=cuerpo, headers=_cabecera(token))

    respuesta = client.post(RUTA_ENROLLMENTS, json=cuerpo, headers=_cabecera(token))

    assert respuesta.status_code == 409
    assert respuesta.json()["error"]["code"] == "ALREADY_ENROLLED"


@pytest.mark.integration
def test_enroll_in_a_full_group_returns_409_with_the_numbers(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    db_session.execute(
        text("UPDATE course_offerings SET enrolled_count = total_capacity WHERE id = :i"),
        {"i": catalogo.offering_grupo_01_id},
    )
    db_session.commit()
    token = _token(client, _crear_cuenta(db_session, catalogo.program_id))

    respuesta = client.post(
        RUTA_ENROLLMENTS,
        json={"course_offering_id": str(catalogo.offering_grupo_01_id)},
        headers=_cabecera(token),
    )

    assert respuesta.status_code == 409
    error = respuesta.json()["error"]
    assert error["code"] == "COURSE_CAPACITY_EXCEEDED"
    # `API.md` documenta que la respuesta lleva capacidad y ocupación: el estudiante necesita
    # ver «40 de 40», no solo «no hay cupo».
    assert error["details"]["capacity"] == 40


@pytest.mark.integration
def test_enroll_in_a_course_outside_the_curriculum_returns_403(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    from app.infrastructure.persistence.sqlalchemy.models.program import ProgramModel

    otro = ProgramModel(id=uuid4(), code="DERE", name="Derecho", total_semesters=10)
    db_session.add(otro)
    db_session.commit()
    token = _token(client, _crear_cuenta(db_session, otro.id))

    respuesta = client.post(
        RUTA_ENROLLMENTS,
        json={"course_offering_id": str(catalogo.offering_grupo_01_id)},
        headers=_cabecera(token),
    )

    # 403 y no 409: no es un conflicto de estado, es una operación que a esta persona no le
    # corresponde hacer.
    assert respuesta.status_code == 403
    assert respuesta.json()["error"]["code"] == "COURSE_NOT_IN_PROGRAM"


@pytest.mark.integration
def test_enroll_in_a_group_that_does_not_exist_returns_404(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    token = _token(client, _crear_cuenta(db_session, catalogo.program_id))

    respuesta = client.post(
        RUTA_ENROLLMENTS,
        json={"course_offering_id": str(uuid4())},
        headers=_cabecera(token),
    )

    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["code"] == "OFFERING_NOT_FOUND"


@pytest.mark.integration
def test_enroll_when_the_period_is_closed_returns_409(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    token = _token(client, _crear_cuenta(db_session, catalogo.program_id))
    db_session.execute(text("UPDATE enrollment_periods SET is_active = FALSE"))
    db_session.commit()

    respuesta = client.post(
        RUTA_ENROLLMENTS,
        json={"course_offering_id": str(catalogo.offering_grupo_01_id)},
        headers=_cabecera(token),
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["error"]["code"] == "ENROLLMENT_PERIOD_INACTIVE"


# ---------------------------------------------------------------------------
# DELETE /enrollments/{id}
# ---------------------------------------------------------------------------


def _inscribir(client: TestClient, token: str, offering_id: UUID) -> str:
    respuesta = client.post(
        RUTA_ENROLLMENTS,
        json={"course_offering_id": str(offering_id)},
        headers=_cabecera(token),
    )
    assert respuesta.status_code == 201, respuesta.text
    return str(respuesta.json()["id"])


@pytest.mark.integration
def test_cancel_returns_204_and_frees_the_seat(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    token = _token(client, _crear_cuenta(db_session, catalogo.program_id))
    inscripcion_id = _inscribir(client, token, catalogo.offering_grupo_01_id)
    ocupados = db_session.execute(
        text("SELECT enrolled_count FROM course_offerings WHERE id = :i"),
        {"i": catalogo.offering_grupo_01_id},
    ).scalar_one()

    respuesta = client.delete(f"{RUTA_ENROLLMENTS}/{inscripcion_id}", headers=_cabecera(token))

    assert respuesta.status_code == 204
    despues = db_session.execute(
        text("SELECT enrolled_count FROM course_offerings WHERE id = :i"),
        {"i": catalogo.offering_grupo_01_id},
    ).scalar_one()
    assert despues == ocupados - 1


@pytest.mark.integration
def test_cancelling_someone_elses_enrollment_returns_404(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    """La autorización, comprobada de extremo a extremo.

    Responde 404 y no 403: distinguirlos confirmaría que ese identificador corresponde a una
    inscripción real, y permitiría enumerarlas.
    """
    token_propietario = _token(client, _crear_cuenta(db_session, catalogo.program_id, sufijo="01"))
    inscripcion_id = _inscribir(client, token_propietario, catalogo.offering_grupo_01_id)
    token_intruso = _token(client, _crear_cuenta(db_session, catalogo.program_id, sufijo="02"))

    respuesta = client.delete(
        f"{RUTA_ENROLLMENTS}/{inscripcion_id}", headers=_cabecera(token_intruso)
    )

    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["code"] == "ENROLLMENT_NOT_FOUND"


@pytest.mark.integration
def test_cancelling_someone_elses_enrollment_does_not_free_their_seat(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    token_propietario = _token(client, _crear_cuenta(db_session, catalogo.program_id, sufijo="01"))
    inscripcion_id = _inscribir(client, token_propietario, catalogo.offering_grupo_01_id)
    ocupados = db_session.execute(
        text("SELECT enrolled_count FROM course_offerings WHERE id = :i"),
        {"i": catalogo.offering_grupo_01_id},
    ).scalar_one()
    token_intruso = _token(client, _crear_cuenta(db_session, catalogo.program_id, sufijo="02"))

    client.delete(f"{RUTA_ENROLLMENTS}/{inscripcion_id}", headers=_cabecera(token_intruso))

    despues = db_session.execute(
        text("SELECT enrolled_count FROM course_offerings WHERE id = :i"),
        {"i": catalogo.offering_grupo_01_id},
    ).scalar_one()
    assert despues == ocupados


@pytest.mark.integration
def test_cancelling_twice_returns_409(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    token = _token(client, _crear_cuenta(db_session, catalogo.program_id))
    inscripcion_id = _inscribir(client, token, catalogo.offering_grupo_01_id)
    client.delete(f"{RUTA_ENROLLMENTS}/{inscripcion_id}", headers=_cabecera(token))

    respuesta = client.delete(f"{RUTA_ENROLLMENTS}/{inscripcion_id}", headers=_cabecera(token))

    assert respuesta.status_code == 409
    assert respuesta.json()["error"]["code"] == "ENROLLMENT_ALREADY_CANCELLED"


@pytest.mark.integration
def test_reenrolling_after_cancelling_works(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    """Cancelar y volver a inscribirse reactiva la fila, no crea otra.

    La restricción `UNIQUE` impide insertar una segunda, así que sin la reactivación este
    camino fallaría con un error de clave duplicada.
    """
    token = _token(client, _crear_cuenta(db_session, catalogo.program_id))
    primera = _inscribir(client, token, catalogo.offering_grupo_01_id)
    client.delete(f"{RUTA_ENROLLMENTS}/{primera}", headers=_cabecera(token))

    segunda = _inscribir(client, token, catalogo.offering_grupo_01_id)

    assert segunda == primera
    filas = db_session.execute(
        text("SELECT count(*) FROM enrollments WHERE course_offering_id = :i"),
        {"i": catalogo.offering_grupo_01_id},
    ).scalar_one()
    assert filas == 1


@pytest.mark.integration
def test_cancel_without_a_token_is_rejected(client: TestClient) -> None:
    assert client.delete(f"{RUTA_ENROLLMENTS}/{uuid4()}").status_code == 401


# ---------------------------------------------------------------------------
# GET /students/me/schedule
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_schedule_with_nothing_enrolled_is_empty(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    token = _token(client, _crear_cuenta(db_session, catalogo.program_id))

    respuesta = client.get(RUTA_HORARIO, headers=_cabecera(token))

    assert respuesta.status_code == 200
    assert respuesta.json()["blocks"] == []


@pytest.mark.integration
def test_schedule_shows_the_enrolled_class_with_its_context(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    token = _token(client, _crear_cuenta(db_session, catalogo.program_id))
    _inscribir(client, token, catalogo.offering_grupo_01_id)

    cuerpo = client.get(RUTA_HORARIO, headers=_cabecera(token)).json()

    assert cuerpo["period"] == "2025-2"
    # El grupo 01 de la fixture se dicta lunes y miércoles.
    assert [b["day_of_week"] for b in cuerpo["blocks"]] == [1, 3]
    assert cuerpo["blocks"][0]["course_code"] == "MAT101"
    assert cuerpo["blocks"][0]["professor"] == "Ana Pérez"
    assert cuerpo["blocks"][0]["classroom"] == "A-201"


@pytest.mark.integration
def test_a_cancelled_class_disappears_from_the_schedule(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    token = _token(client, _crear_cuenta(db_session, catalogo.program_id))
    inscripcion_id = _inscribir(client, token, catalogo.offering_grupo_01_id)
    assert client.get(RUTA_HORARIO, headers=_cabecera(token)).json()["blocks"]

    client.delete(f"{RUTA_ENROLLMENTS}/{inscripcion_id}", headers=_cabecera(token))

    assert client.get(RUTA_HORARIO, headers=_cabecera(token)).json()["blocks"] == []


@pytest.mark.integration
def test_the_schedule_only_shows_your_own_classes(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    token_uno = _token(client, _crear_cuenta(db_session, catalogo.program_id, sufijo="01"))
    _inscribir(client, token_uno, catalogo.offering_grupo_01_id)
    token_dos = _token(client, _crear_cuenta(db_session, catalogo.program_id, sufijo="02"))

    assert client.get(RUTA_HORARIO, headers=_cabecera(token_dos)).json()["blocks"] == []


@pytest.mark.integration
def test_schedule_without_a_token_is_rejected(client: TestClient) -> None:
    assert client.get(RUTA_HORARIO).status_code == 401


# ---------------------------------------------------------------------------
# GET /students/me/enrollments
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_listado_de_inscripciones_vacio_no_es_un_error(
    client: TestClient, db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    """Todavía no ha inscrito nada: es un resultado legítimo, no un fallo."""
    credenciales = _crear_cuenta(db_session, catalogo.program_id, "70")
    cabecera = {"Authorization": f"Bearer {_token(client, credenciales)}"}

    respuesta = client.get("/api/v1/students/me/enrollments", headers=cabecera)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["items"] == []
    assert cuerpo["total_credits"] == 0
    assert cuerpo["period_code"] == "2025-2-V1"


@pytest.mark.integration
def test_el_listado_trae_el_id_con_el_que_se_cancela(
    client: TestClient, db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    """Es la razón de ser del endpoint: el horario no lleva el identificador de la inscripción.

    Se comprueba de la forma más contundente posible: cancelando con el identificador que
    devolvió el listado. Si no fuera el correcto, la cancelación respondería 404.
    """
    credenciales = _crear_cuenta(db_session, catalogo.program_id, "71")
    cabecera = {"Authorization": f"Bearer {_token(client, credenciales)}"}

    inscripcion = client.post(
        RUTA_ENROLLMENTS,
        json={"course_offering_id": str(catalogo.offering_grupo_02_id)},
        headers=cabecera,
    )
    assert inscripcion.status_code == 201, inscripcion.text

    listado = client.get("/api/v1/students/me/enrollments", headers=cabecera)
    assert listado.status_code == 200, listado.text
    cuerpo = listado.json()

    assert len(cuerpo["items"]) == 1
    item = cuerpo["items"][0]
    assert item["course_code"] == "MAT101"
    assert item["group_number"] == "02"
    # Los créditos se suman en el servidor para que la cifra sea la misma en la pantalla y en
    # el comprobante en PDF.
    assert cuerpo["total_credits"] == item["credits"]

    cancelacion = client.delete(f"{RUTA_ENROLLMENTS}/{item['id']}", headers=cabecera)
    assert cancelacion.status_code == 204, cancelacion.text


@pytest.mark.integration
def test_el_listado_omite_las_inscripciones_canceladas(
    client: TestClient, db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    """Las canceladas no ocupan cupo ni aparecen en el horario: tampoco deben aparecer aquí."""
    credenciales = _crear_cuenta(db_session, catalogo.program_id, "72")
    cabecera = {"Authorization": f"Bearer {_token(client, credenciales)}"}

    inscripcion = client.post(
        RUTA_ENROLLMENTS,
        json={"course_offering_id": str(catalogo.offering_grupo_02_id)},
        headers=cabecera,
    )
    enrollment_id = inscripcion.json()["id"]
    assert client.delete(f"{RUTA_ENROLLMENTS}/{enrollment_id}", headers=cabecera).status_code == 204

    listado = client.get("/api/v1/students/me/enrollments", headers=cabecera)

    assert listado.json()["items"] == []
    assert listado.json()["total_credits"] == 0


@pytest.mark.integration
def test_nadie_puede_ver_las_inscripciones_de_otro(client: TestClient) -> None:
    """El estudiante sale del token, nunca de la petición."""
    respuesta = client.get("/api/v1/students/me/enrollments")

    assert respuesta.status_code == 401, respuesta.text
