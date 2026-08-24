"""Pruebas de la autorización por rol de los endpoints de administración.

`DEVELOPMENT_WORKFLOW.md` las pide explícitamente entre los entregables de la Fase 4: *«un
estudiante intentando llamar endpoints de admin debe recibir 403»*.

Que el guard `require_admin` exista desde la Fase 1 no significa que esté cableado. Estos tests
comprueban lo segundo, que es lo que de verdad protege: un guard perfecto que nadie aplica no
impide nada. Por eso recorren la petición completa, con token real, en vez de llamar a la
función del guard directamente.

Hay además un test que recorre **todas** las rutas bajo `/admin` registradas en la aplicación y
comprueba que ninguna quedó sin proteger. Es el que sigue funcionando cuando se añadan los
endpoints de las iteraciones siguientes sin que nadie se acuerde de volver aquí.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.infrastructure.auth.jwt_auth_service import JWTAuthService
from app.infrastructure.config.settings import get_settings
from app.infrastructure.persistence.sqlalchemy.models.administrator import AdministratorModel
from app.infrastructure.persistence.sqlalchemy.models.student import StudentModel
from app.infrastructure.persistence.sqlalchemy.models.user import UserModel
from app.interfaces.api.main import app
from tests.integration.conftest import CatalogoDePrueba

RUTA_PERIODOS = "/api/v1/admin/enrollment-periods"
PASSWORD = "SecurePass123"


def _cuenta_admin(db_session: Session) -> dict[str, str]:
    """Crea una cuenta con rol ADMIN y su perfil administrativo."""
    hasher = JWTAuthService(get_settings())

    usuario = UserModel(
        id=uuid4(),
        email="admin.autorizacion@tdea.edu.co",
        password_hash=hasher.hash(PASSWORD),
        role="ADMIN",
        is_active=True,
    )
    db_session.add(usuario)
    db_session.flush()
    db_session.add(
        AdministratorModel(
            id=uuid4(),
            user_id=usuario.id,
            full_name="Administración de Pruebas",
            department="Registro y Control",
        )
    )
    db_session.commit()

    return {"email": usuario.email, "password": PASSWORD}


def _cuenta_estudiante(db_session: Session, catalogo: CatalogoDePrueba) -> dict[str, str]:
    """Crea una cuenta con rol STUDENT."""
    from datetime import date

    hasher = JWTAuthService(get_settings())

    usuario = UserModel(
        id=uuid4(),
        email="estudiante.autorizacion@tdea.edu.co",
        password_hash=hasher.hash(PASSWORD),
        role="STUDENT",
        is_active=True,
    )
    db_session.add(usuario)
    db_session.flush()
    db_session.add(
        StudentModel(
            id=uuid4(),
            user_id=usuario.id,
            student_code="5000001",
            program_id=catalogo.program_id,
            current_semester=1,
            full_name="Estudiante De Autorización",
            enrollment_date=date(2022, 1, 15),
        )
    )
    db_session.commit()

    return {"email": usuario.email, "password": PASSWORD}


def _token(client: TestClient, credenciales: dict[str, str]) -> str:
    respuesta = client.post("/api/v1/auth/login", json=credenciales)
    assert respuesta.status_code == 200, respuesta.text
    return str(respuesta.json()["access_token"])


def _periodo_valido() -> dict[str, str]:
    ahora = datetime.now(UTC)
    return {
        "code": f"AUT-{uuid4().hex[:6].upper()}",
        "academic_period": "2026-1",
        "name": "Matrícula de prueba",
        "starts_at": (ahora + timedelta(days=1)).isoformat(),
        "ends_at": (ahora + timedelta(days=3)).isoformat(),
    }


# ---------------------------------------------------------------------------
# Los tres estados de la autorización
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_admin_endpoint_without_a_token_returns_401(client: TestClient) -> None:
    respuesta = client.post(RUTA_PERIODOS, json=_periodo_valido())

    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["code"] == "MISSING_TOKEN"


@pytest.mark.integration
def test_admin_endpoint_with_a_student_token_returns_403(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    """El entregable que pide `DEVELOPMENT_WORKFLOW.md` para esta fase.

    Un estudiante autenticado recibe 403, no 401: su identidad quedó probada, lo que falta es
    el permiso. Devolver 401 haría que el cliente intentara volver a autenticarse, lo que no
    arreglaría nada.
    """
    token = _token(client, _cuenta_estudiante(db_session, catalogo))

    respuesta = client.post(
        RUTA_PERIODOS, json=_periodo_valido(), headers={"Authorization": f"Bearer {token}"}
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["error"]["code"] == "ADMIN_REQUIRED"


@pytest.mark.integration
def test_admin_endpoint_with_an_admin_token_is_allowed(
    client: TestClient, db_session: Session
) -> None:
    token = _token(client, _cuenta_admin(db_session))

    respuesta = client.post(
        RUTA_PERIODOS, json=_periodo_valido(), headers={"Authorization": f"Bearer {token}"}
    )

    assert respuesta.status_code == 201


@pytest.mark.integration
def test_admin_endpoint_with_a_forged_token_returns_401(client: TestClient) -> None:
    respuesta = client.post(
        RUTA_PERIODOS,
        json=_periodo_valido(),
        headers={"Authorization": "Bearer esto-no-es-un-token"},
    )

    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["code"] == "INVALID_TOKEN"


@pytest.mark.integration
def test_a_refresh_token_does_not_open_the_admin_area(
    client: TestClient, db_session: Session
) -> None:
    # El refresh token dura 7 días. Si sirviera para llamar a la API, la ventana de exposición
    # de un token robado pasaría de una hora a una semana, y encima sobre endpoints de
    # administración.
    respuesta_login = client.post("/api/v1/auth/login", json=_cuenta_admin(db_session))
    refresh = respuesta_login.json()["refresh_token"]

    respuesta = client.post(
        RUTA_PERIODOS, json=_periodo_valido(), headers={"Authorization": f"Bearer {refresh}"}
    )

    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["code"] == "INVALID_TOKEN"


@pytest.mark.integration
def test_a_deactivated_admin_cannot_log_in(client: TestClient, db_session: Session) -> None:
    credenciales = _cuenta_admin(db_session)
    usuario = db_session.query(UserModel).filter_by(email=credenciales["email"]).one()
    usuario.is_active = False
    db_session.commit()

    respuesta = client.post("/api/v1/auth/login", json=credenciales)

    assert respuesta.status_code == 403
    assert respuesta.json()["error"]["code"] == "USER_INACTIVE"


# ---------------------------------------------------------------------------
# La red que cubre los endpoints que aún no existen
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_every_admin_route_declares_the_guard() -> None:
    """Ninguna ruta bajo `/admin` puede quedar sin proteger.

    Este test recorre la aplicación real y no una lista escrita a mano, así que **sigue
    protegiendo cuando se añadan los endpoints de las iteraciones siguientes**. Ese es su
    valor: el fallo que previene no es olvidarse del guard hoy, sino olvidarse dentro de dos
    semanas al añadir el endpoint de reportes.

    Un endpoint de administración sin guard quedaría abierto a cualquier estudiante
    autenticado, y nada fallaría de forma visible: respondería 200 con toda normalidad.
    """
    from app.interfaces.api.dependencies.auth import require_admin

    rutas_admin = [r for r in app.routes if isinstance(r, APIRoute) and "/admin" in r.path]

    assert rutas_admin, "no hay rutas /admin registradas; el router no está montado"

    for ruta in rutas_admin:
        protegida = any(dep.call is require_admin for dep in ruta.dependant.dependencies) or any(
            sub.call is require_admin
            for dep in ruta.dependant.dependencies
            for sub in dep.dependencies
        )
        assert protegida, f"la ruta {ruta.path} no exige rol de administrador"


@pytest.mark.integration
def test_no_admin_route_is_reachable_by_a_student(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    """Lo mismo, pero comprobado por el comportamiento y no por la declaración.

    El test anterior mira cómo está declarada la ruta; este envía peticiones reales con un
    token de estudiante. Los dos son necesarios: una ruta podría declarar el guard y aun así
    responder si algo del cableado fallara, y a la inversa.
    """
    token = _token(client, _cuenta_estudiante(db_session, catalogo))
    cabecera = {"Authorization": f"Bearer {token}"}

    for ruta in [r for r in app.routes if isinstance(r, APIRoute) and "/admin" in r.path]:
        for metodo in ruta.methods - {"HEAD", "OPTIONS"}:
            # Los parámetros de ruta se rellenan con un UUID cualquiera: la autorización se
            # comprueba antes de que el identificador importe.
            camino = ruta.path
            for parametro in ("{period_id}", "{offering_id}", "{course_id}", "{id}"):
                camino = camino.replace(parametro, str(uuid4()))

            respuesta = client.request(metodo, camino, json={}, headers=cabecera)

            assert (
                respuesta.status_code == 403
            ), f"{metodo} {camino} respondió {respuesta.status_code} a un estudiante"
