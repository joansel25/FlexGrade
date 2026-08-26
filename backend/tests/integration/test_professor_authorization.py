"""Pruebas de la autorización del docente (iteración 9.1).

Es el mismo planteamiento que `test_admin_authorization.py`, aplicado al rol que la Fase 9
introduce, y por la misma razón: que `require_professor` exista no significa que esté cableado.
Un guard perfecto que nadie aplica no impide nada.

Lo que estas pruebas fijan y que no es obvio:

**Un administrador NO puede entrar por `/professors`.** Es deliberado y va contra el reflejo de
que «admin puede todo». Quien conoce la nota es quien dictó la clase; dejar que la ponga
cualquiera con permiso amplio borra esa responsabilidad, que es justamente lo que la 9.2 va a
necesitar que esté clara.

**Rol sin perfil responde 404 y no 403.** Se distingue porque los dos errores se corrigen en
sitios distintos: el 403 se arregla cambiando el rol, y el 404 dando de alta al docente. Un
único código mandaría a la mitad de los casos al sitio equivocado.

Hay además un test que recorre TODAS las rutas bajo `/professors` registradas en la aplicación.
Es el que sigue funcionando cuando la 9.2 añada el registro de notas sin que nadie se acuerde
de volver aquí.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.infrastructure.auth.jwt_auth_service import JWTAuthService
from app.infrastructure.config.settings import get_settings
from app.infrastructure.persistence.sqlalchemy.models.administrator import AdministratorModel
from app.infrastructure.persistence.sqlalchemy.models.professor import ProfessorModel
from app.infrastructure.persistence.sqlalchemy.models.student import StudentModel
from app.infrastructure.persistence.sqlalchemy.models.user import UserModel
from app.interfaces.api.main import app
from tests.integration.conftest import CatalogoDePrueba

RUTA_CARGA = "/api/v1/professors/me/offerings"
PASSWORD = "SecurePass123"


def _cuenta(db_session: Session, *, correo: str, rol: str) -> UserModel:
    hasher = JWTAuthService(get_settings())
    usuario = UserModel(
        id=uuid4(),
        email=correo,
        password_hash=hasher.hash(PASSWORD),
        role=rol,
        is_active=True,
    )
    db_session.add(usuario)
    db_session.flush()

    return usuario


def _cuenta_docente(db_session: Session, *, con_perfil: bool = True) -> dict[str, str]:
    """Crea una cuenta con rol PROFESSOR, con o sin su perfil enlazado.

    El caso sin perfil no es teórico: es lo que pasa cuando se le da el rol a una cuenta y se
    olvida enlazarla a una fila de `professors`, que es un error de alta y no de permisos.
    """
    correo = f"docente.{uuid4().hex[:8]}@tdea.edu.co"
    usuario = _cuenta(db_session, correo=correo, rol="PROFESSOR")

    if con_perfil:
        db_session.add(
            ProfessorModel(
                id=uuid4(),
                full_name="Docente De Pruebas",
                email=correo,
                user_id=usuario.id,
            )
        )

    db_session.commit()

    return {"email": correo, "password": PASSWORD}


def _cuenta_admin(db_session: Session) -> dict[str, str]:
    correo = f"admin.{uuid4().hex[:8]}@tdea.edu.co"
    usuario = _cuenta(db_session, correo=correo, rol="ADMIN")
    db_session.add(
        AdministratorModel(
            id=uuid4(),
            user_id=usuario.id,
            full_name="Administración de Pruebas",
            department="Registro y Control",
        )
    )
    db_session.commit()

    return {"email": correo, "password": PASSWORD}


def _cuenta_estudiante(db_session: Session, catalogo: CatalogoDePrueba) -> dict[str, str]:
    correo = f"estudiante.{uuid4().hex[:8]}@tdea.edu.co"
    usuario = _cuenta(db_session, correo=correo, rol="STUDENT")
    db_session.add(
        StudentModel(
            id=uuid4(),
            user_id=usuario.id,
            student_code=f"9{uuid4().int % 1_000_000_000:09d}",
            program_id=catalogo.program_id,
            current_semester=1,
            full_name="Estudiante De Pruebas",
            enrollment_date=date(2022, 1, 15),
        )
    )
    db_session.commit()

    return {"email": correo, "password": PASSWORD}


def _token(client: TestClient, credenciales: dict[str, str]) -> str:
    respuesta = client.post("/api/v1/auth/login", json=credenciales)
    assert respuesta.status_code == 200, respuesta.text

    return str(respuesta.json()["access_token"])


@pytest.mark.integration
def test_un_docente_ve_su_carga(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    token = _token(client, _cuenta_docente(db_session))

    respuesta = client.get(RUTA_CARGA, headers={"Authorization": f"Bearer {token}"})

    assert respuesta.status_code == 200
    assert respuesta.json()["items"] == []


@pytest.mark.integration
def test_un_estudiante_no_puede_entrar(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    token = _token(client, _cuenta_estudiante(db_session, catalogo))

    respuesta = client.get(RUTA_CARGA, headers={"Authorization": f"Bearer {token}"})

    assert respuesta.status_code == 403
    assert respuesta.json()["error"]["code"] == "PROFESSOR_REQUIRED"


@pytest.mark.integration
def test_un_administrador_tampoco_puede_entrar(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    """Va contra el reflejo de que «admin puede todo», y es a propósito.

    Quien conoce la nota es quien dictó la clase. Si un administrador pudiera calificar por el
    hecho de serlo, la responsabilidad de la nota dejaría de estar en ningún sitio concreto, y
    la 9.2 necesita que esté clara.
    """
    token = _token(client, _cuenta_admin(db_session))

    respuesta = client.get(RUTA_CARGA, headers={"Authorization": f"Bearer {token}"})

    assert respuesta.status_code == 403
    assert respuesta.json()["error"]["code"] == "PROFESSOR_REQUIRED"


@pytest.mark.integration
def test_rol_de_docente_sin_perfil_responde_que_falta_el_alta(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    # 404 y no 403: el permiso está, lo que falta es la fila en `professors`. Responder 403
    # mandaría a corregir el rol, que es justo lo único que sí está bien.
    token = _token(client, _cuenta_docente(db_session, con_perfil=False))

    respuesta = client.get(RUTA_CARGA, headers={"Authorization": f"Bearer {token}"})

    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["code"] == "PROFESSOR_PROFILE_NOT_FOUND"


@pytest.mark.integration
def test_sin_token_no_se_llega(client: TestClient) -> None:
    respuesta = client.get(RUTA_CARGA)

    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["code"] == "MISSING_TOKEN"


@pytest.mark.integration
def test_toda_ruta_de_docente_declara_el_guard() -> None:
    """Ninguna ruta bajo `/professors` puede quedar sin proteger.

    Recorre la aplicación real y no una lista escrita a mano, así que **sigue protegiendo
    cuando la 9.2 añada el registro de notas**. Ese es su valor: el fallo que previene no es
    olvidarse del guard hoy, sino dentro de dos semanas.
    """
    from app.interfaces.api.dependencies.auth import get_current_professor, require_professor

    rutas = [r for r in app.routes if isinstance(r, APIRoute) and "/professors" in r.path]

    assert rutas, "no hay rutas /professors registradas; el router no está montado"

    for ruta in rutas:
        # Vale cualquiera de los dos: `get_current_professor` ya depende de
        # `require_professor`, así que exigirlo suelto obligaría a declararlo dos veces.
        guardas = {dep.call for dep in ruta.dependant.dependencies} | {
            sub.call for dep in ruta.dependant.dependencies for sub in dep.dependencies
        }
        assert guardas & {
            require_professor,
            get_current_professor,
        }, f"la ruta {ruta.path} no exige rol de docente"
