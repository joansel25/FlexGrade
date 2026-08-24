"""Pruebas de integración del catálogo y los cupos de administración (iteración 4.3).

Estos tres endpoints escriben en las tablas más restringidas del esquema, y casi todo lo que
protegen vive en PostgreSQL: la restricción `UNIQUE` de `courses.code`, la de
`(enrollment_period_id, course_id, group_number)` en `course_offerings` y el
`CHECK (enrolled_count <= total_capacity)`. Un doble en memoria no tiene ninguna de las tres,
así que solo aquí se puede comprobar que las comprobaciones del caso de uso y las de la base
dicen lo mismo.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infrastructure.auth.jwt_auth_service import JWTAuthService
from app.infrastructure.config.settings import get_settings
from app.infrastructure.persistence.sqlalchemy.models.administrator import AdministratorModel
from app.infrastructure.persistence.sqlalchemy.models.course_offering import CourseOfferingModel
from app.infrastructure.persistence.sqlalchemy.models.schedule_block import ScheduleBlockModel
from app.infrastructure.persistence.sqlalchemy.models.user import UserModel
from tests.integration.conftest import CatalogoDePrueba

RUTA_MATERIAS = "/api/v1/admin/courses"
RUTA_GRUPOS = "/api/v1/admin/offerings"
PASSWORD = "SecurePass123"


@pytest.fixture
def admin(client: TestClient, db_session: Session) -> dict[str, str]:
    """Devuelve la cabecera de autorización de una cuenta con rol ADMIN."""
    hasher = JWTAuthService(get_settings())

    usuario = UserModel(
        id=uuid4(),
        email="admin.catalogo@tdea.edu.co",
        password_hash=hasher.hash(PASSWORD),
        role="ADMIN",
        is_active=True,
    )
    db_session.add(usuario)
    db_session.flush()
    db_session.add(
        AdministratorModel(
            id=uuid4(), user_id=usuario.id, full_name="Admin Catálogo", department="Registro"
        )
    )
    db_session.commit()

    respuesta = client.post(
        "/api/v1/auth/login", json={"email": usuario.email, "password": PASSWORD}
    )
    assert respuesta.status_code == 200, respuesta.text
    return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}


# ---------------------------------------------------------------------------
# POST /admin/courses
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_crear_materia_devuelve_201_y_queda_en_el_catalogo(
    client: TestClient, admin: dict[str, str], db_session: Session
) -> None:
    respuesta = client.post(
        RUTA_MATERIAS,
        json={"code": "qui101", "name": "Química General", "credits": 3},
        headers=admin,
    )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    # El código viaja normalizado: el value object lo pasa a mayúsculas antes de persistirlo.
    assert cuerpo["code"] == "QUI101"

    detalle = client.get(f"/api/v1/courses/{cuerpo['id']}")
    assert detalle.status_code == 200, detalle.text
    assert detalle.json()["name"] == "Química General"


@pytest.mark.integration
def test_crear_materia_con_codigo_repetido_devuelve_409(
    client: TestClient, admin: dict[str, str], catalogo: CatalogoDePrueba
) -> None:
    """La restricción UNIQUE también lo impediría, pero con un mensaje que no dice qué hacer."""
    respuesta = client.post(
        RUTA_MATERIAS,
        json={"code": "MAT101", "name": "Cálculo I bis", "credits": 4},
        headers=admin,
    )

    assert respuesta.status_code == 409, respuesta.text
    assert respuesta.json()["error"]["code"] == "DUPLICATE_COURSE_CODE"


@pytest.mark.integration
def test_crear_materia_con_codigo_mal_formado_devuelve_400(
    client: TestClient, admin: dict[str, str]
) -> None:
    respuesta = client.post(
        RUTA_MATERIAS, json={"code": "101", "name": "Sin área", "credits": 4}, headers=admin
    )

    assert respuesta.status_code == 400, respuesta.text


@pytest.mark.integration
def test_crear_materia_sin_token_devuelve_401(client: TestClient) -> None:
    respuesta = client.post(RUTA_MATERIAS, json={"code": "QUI102", "name": "Q", "credits": 1})

    assert respuesta.status_code == 401, respuesta.text


# ---------------------------------------------------------------------------
# POST /admin/offerings
# ---------------------------------------------------------------------------


def _cuerpo_de_grupo(catalogo: CatalogoDePrueba, group_number: str = "03") -> dict[str, object]:
    return {
        "course_id": str(catalogo.calculo_i_id),
        "professor_id": str(catalogo.professor_id),
        "group_number": group_number,
        "total_capacity": 40,
        "schedule": [
            {
                "day_of_week": 2,
                "start_time": "10:00",
                "end_time": "12:00",
                "classroom": "B-101",
            }
        ],
    }


@pytest.mark.integration
def test_crear_grupo_lo_publica_en_el_periodo_activo_con_su_horario(
    client: TestClient,
    admin: dict[str, str],
    catalogo: CatalogoDePrueba,
    db_session: Session,
) -> None:
    respuesta = client.post(RUTA_GRUPOS, json=_cuerpo_de_grupo(catalogo), headers=admin)

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["enrollment_period_id"] == str(catalogo.period_id)
    assert cuerpo["available_slots"] == 40
    # El docente viaja resuelto, igual que en `GET /offerings/{id}`.
    assert cuerpo["professor"] == "Ana Pérez"

    franjas = db_session.execute(
        select(func.count())
        .select_from(ScheduleBlockModel)
        .where(ScheduleBlockModel.course_offering_id == UUID(cuerpo["id"]))
    ).scalar_one()
    assert franjas == 1


@pytest.mark.integration
def test_el_grupo_creado_aparece_en_el_catalogo_publico(
    client: TestClient, admin: dict[str, str], catalogo: CatalogoDePrueba
) -> None:
    """El recorrido completo: se abre el grupo y un estudiante ya lo ve con su cupo libre."""
    creado = client.post(RUTA_GRUPOS, json=_cuerpo_de_grupo(catalogo), headers=admin)
    assert creado.status_code == 201, creado.text

    grupos = client.get(f"/api/v1/courses/{catalogo.calculo_i_id}/offerings")
    assert grupos.status_code == 200, grupos.text
    numeros = [g["group_number"] for g in grupos.json()["offerings"]]
    assert "03" in numeros


@pytest.mark.integration
def test_crear_grupo_con_numero_repetido_devuelve_409(
    client: TestClient, admin: dict[str, str], catalogo: CatalogoDePrueba
) -> None:
    """`01` ya existe para Cálculo I en el período activo."""
    respuesta = client.post(
        RUTA_GRUPOS, json=_cuerpo_de_grupo(catalogo, group_number="01"), headers=admin
    )

    assert respuesta.status_code == 409, respuesta.text
    assert respuesta.json()["error"]["code"] == "DUPLICATE_OFFERING_GROUP"


@pytest.mark.integration
def test_crear_grupo_con_docente_inexistente_devuelve_404(
    client: TestClient, admin: dict[str, str], catalogo: CatalogoDePrueba
) -> None:
    """Sin la comprobación previa, la clave foránea daría un 500 en vez de este 404."""
    cuerpo = _cuerpo_de_grupo(catalogo)
    cuerpo["professor_id"] = str(uuid4())

    respuesta = client.post(RUTA_GRUPOS, json=cuerpo, headers=admin)

    assert respuesta.status_code == 404, respuesta.text
    assert respuesta.json()["error"]["code"] == "PROFESSOR_NOT_FOUND"


@pytest.mark.integration
def test_crear_grupo_con_materia_inexistente_devuelve_404(
    client: TestClient, admin: dict[str, str], catalogo: CatalogoDePrueba
) -> None:
    cuerpo = _cuerpo_de_grupo(catalogo)
    cuerpo["course_id"] = str(uuid4())

    respuesta = client.post(RUTA_GRUPOS, json=cuerpo, headers=admin)

    assert respuesta.status_code == 404, respuesta.text
    assert respuesta.json()["error"]["code"] == "COURSE_NOT_FOUND"


@pytest.mark.integration
def test_crear_grupo_con_horario_solapado_devuelve_409(
    client: TestClient, admin: dict[str, str], catalogo: CatalogoDePrueba
) -> None:
    cuerpo = _cuerpo_de_grupo(catalogo)
    cuerpo["schedule"] = [
        {"day_of_week": 2, "start_time": "10:00", "end_time": "12:00", "classroom": "B-101"},
        {"day_of_week": 2, "start_time": "11:00", "end_time": "13:00", "classroom": "B-102"},
    ]

    respuesta = client.post(RUTA_GRUPOS, json=cuerpo, headers=admin)

    assert respuesta.status_code == 409, respuesta.text
    assert respuesta.json()["error"]["code"] == "OVERLAPPING_SCHEDULE"


@pytest.mark.integration
def test_crear_grupo_con_cupo_no_positivo_devuelve_422(
    client: TestClient, admin: dict[str, str], catalogo: CatalogoDePrueba
) -> None:
    """Lo rechaza el schema antes de llegar al `CHECK (total_capacity > 0)` de PostgreSQL."""
    cuerpo = _cuerpo_de_grupo(catalogo)
    cuerpo["total_capacity"] = 0

    respuesta = client.post(RUTA_GRUPOS, json=cuerpo, headers=admin)

    assert respuesta.status_code == 422, respuesta.text


# ---------------------------------------------------------------------------
# PUT /admin/offerings/{id}/capacity
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_ampliar_el_cupo_lo_persiste_y_refresca_el_catalogo(
    client: TestClient,
    admin: dict[str, str],
    catalogo: CatalogoDePrueba,
    db_session: Session,
) -> None:
    """Comprueba la invalidación de caché: se consulta ANTES de ajustar para poblarla.

    Sin el `delete` del caso de uso, la segunda consulta seguiría sirviendo el cupo viejo desde
    Redis durante todo el TTL, junto a un `enrolled_count` fresco: dos datos de momentos
    distintos en la misma respuesta.
    """
    ruta_publica = f"/api/v1/offerings/{catalogo.offering_grupo_01_id}"
    antes = client.get(ruta_publica)
    assert antes.status_code == 200, antes.text
    assert antes.json()["total_capacity"] == 40

    respuesta = client.put(
        f"{RUTA_GRUPOS}/{catalogo.offering_grupo_01_id}/capacity",
        json={"total_capacity": 60},
        headers=admin,
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["total_capacity"] == 60
    # 60 - 37 inscritos.
    assert respuesta.json()["available_slots"] == 23

    despues = client.get(ruta_publica)
    assert despues.json()["total_capacity"] == 60

    db_session.expire_all()
    fila = db_session.get(CourseOfferingModel, catalogo.offering_grupo_01_id)
    assert fila is not None
    assert fila.total_capacity == 60
    # La versión se mueve en cada modificación del cupo: es la marca del bloqueo optimista.
    assert fila.version == 1


@pytest.mark.integration
def test_reducir_el_cupo_por_debajo_de_los_inscritos_devuelve_409(
    client: TestClient,
    admin: dict[str, str],
    catalogo: CatalogoDePrueba,
    db_session: Session,
) -> None:
    """El grupo 01 tiene 37 inscritos: bajarlo a 10 dejaría fuera a 27 personas.

    Es la comprobación que evita chocar contra `CHECK (enrolled_count <= total_capacity)`, que
    abortaría la transacción con un error de restricción en vez de explicar el problema.
    """
    respuesta = client.put(
        f"{RUTA_GRUPOS}/{catalogo.offering_grupo_01_id}/capacity",
        json={"total_capacity": 10},
        headers=admin,
    )

    assert respuesta.status_code == 409, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["error"]["code"] == "CAPACITY_BELOW_ENROLLED"
    assert cuerpo["error"]["details"]["enrolled_count"] == 37

    db_session.expire_all()
    fila = db_session.get(CourseOfferingModel, catalogo.offering_grupo_01_id)
    assert fila is not None
    assert fila.total_capacity == 40


@pytest.mark.integration
def test_reducir_el_cupo_hasta_los_inscritos_deja_el_grupo_lleno(
    client: TestClient, admin: dict[str, str], catalogo: CatalogoDePrueba
) -> None:
    """Cerrar el grupo en su ocupación exacta es válido: nadie queda expulsado."""
    respuesta = client.put(
        f"{RUTA_GRUPOS}/{catalogo.offering_grupo_01_id}/capacity",
        json={"total_capacity": 37},
        headers=admin,
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["available_slots"] == 0


@pytest.mark.integration
def test_ajustar_el_cupo_de_un_grupo_inexistente_devuelve_404(
    client: TestClient, admin: dict[str, str]
) -> None:
    respuesta = client.put(
        f"{RUTA_GRUPOS}/{uuid4()}/capacity", json={"total_capacity": 10}, headers=admin
    )

    assert respuesta.status_code == 404, respuesta.text
    assert respuesta.json()["error"]["code"] == "OFFERING_NOT_FOUND"


@pytest.mark.integration
def test_un_estudiante_no_puede_tocar_el_catalogo(
    client: TestClient, estudiante_registrado: dict[str, str], catalogo: CatalogoDePrueba
) -> None:
    """La protección la declara el router entero, no cada endpoint."""
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": estudiante_registrado["email"],
            "password": estudiante_registrado["password"],
        },
    )
    assert login.status_code == 200, login.text
    cabecera = {"Authorization": f"Bearer {login.json()['access_token']}"}

    for respuesta in (
        client.post(
            RUTA_MATERIAS,
            json={"code": "QUI103", "name": "Química", "credits": 3},
            headers=cabecera,
        ),
        client.post(RUTA_GRUPOS, json=_cuerpo_de_grupo(catalogo), headers=cabecera),
        client.put(
            f"{RUTA_GRUPOS}/{catalogo.offering_grupo_01_id}/capacity",
            json={"total_capacity": 50},
            headers=cabecera,
        ),
    ):
        assert respuesta.status_code == 403, respuesta.text
        assert respuesta.json()["error"]["code"] == "ADMIN_REQUIRED"
