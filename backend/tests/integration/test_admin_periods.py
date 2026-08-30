"""Pruebas de integración de la gestión de ventanas de matrícula.

El corazón de este archivo es la activación. Cambia dos filas y el esquema prohíbe el estado
intermedio —`ix_enrollment_periods_active` es un índice único parcial—, así que la garantía
solo se puede comprobar contra PostgreSQL real: un doble en memoria no tiene ese índice y
dejaría pasar el error que este archivo existe para detectar.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infrastructure.auth.jwt_auth_service import JWTAuthService
from app.infrastructure.config.settings import get_settings
from app.infrastructure.persistence.sqlalchemy.models.administrator import AdministratorModel
from app.infrastructure.persistence.sqlalchemy.models.enrollment_period import EnrollmentPeriodModel
from app.infrastructure.persistence.sqlalchemy.models.user import UserModel

RUTA = "/api/v1/admin/enrollment-periods"
PASSWORD = "SecurePass123"


@pytest.fixture
def admin(client: TestClient, db_session: Session) -> dict[str, str]:
    """Devuelve la cabecera de autorización de una cuenta con rol ADMIN."""
    hasher = JWTAuthService(get_settings())

    usuario = UserModel(
        id=uuid4(),
        email="admin.periodos@tdea.edu.co",
        password_hash=hasher.hash(PASSWORD),
        role="ADMIN",
        is_active=True,
    )
    db_session.add(usuario)
    db_session.flush()
    db_session.add(
        AdministratorModel(
            id=uuid4(), user_id=usuario.id, full_name="Admin Períodos", department="Registro"
        )
    )
    db_session.commit()

    respuesta = client.post(
        "/api/v1/auth/login", json={"email": usuario.email, "password": PASSWORD}
    )
    assert respuesta.status_code == 200, respuesta.text
    return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}


def _cuerpo(code: str = "2026-1-V1", dias_hasta_apertura: int = 1) -> dict[str, str]:
    ahora = datetime.now(UTC)
    return {
        "code": code,
        "academic_period": "2026-1",
        "name": f"Matrícula {code}",
        "starts_at": (ahora + timedelta(days=dias_hasta_apertura)).isoformat(),
        "ends_at": (ahora + timedelta(days=dias_hasta_apertura + 5)).isoformat(),
    }


def _crear(client: TestClient, admin: dict[str, str], code: str = "2026-1-V1") -> UUID:
    respuesta = client.post(RUTA, json=_cuerpo(code), headers=admin)
    assert respuesta.status_code == 201, respuesta.text
    return UUID(respuesta.json()["id"])


def _activos(db_session: Session) -> int:
    db_session.expire_all()
    return int(
        db_session.execute(
            select(func.count())
            .select_from(EnrollmentPeriodModel)
            .where(EnrollmentPeriodModel.is_active.is_(True))
        ).scalar_one()
    )


# ---------------------------------------------------------------------------
# Creación
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_a_new_period_is_born_deactivated(client: TestClient, admin: dict[str, str]) -> None:
    """Crear y abrir son operaciones distintas.

    Permite preparar la ventana con antelación —revisando fechas, creando sus grupos— sin que
    se abra sola al llegar la fecha.
    """
    respuesta = client.post(RUTA, json=_cuerpo(), headers=admin)

    assert respuesta.status_code == 201
    assert respuesta.json()["is_active"] is False


@pytest.mark.integration
def test_creating_a_period_with_a_repeated_code_is_rejected(
    client: TestClient, admin: dict[str, str]
) -> None:
    client.post(RUTA, json=_cuerpo("2026-1-V1"), headers=admin)

    respuesta = client.post(RUTA, json=_cuerpo("2026-1-V1"), headers=admin)

    assert respuesta.status_code == 409
    assert respuesta.json()["error"]["code"] == "DUPLICATE_PERIOD_CODE"


@pytest.mark.integration
def test_creating_a_period_that_ends_before_it_starts_is_rejected(
    client: TestClient, admin: dict[str, str]
) -> None:
    ahora = datetime.now(UTC)
    cuerpo = _cuerpo()
    cuerpo["starts_at"] = (ahora + timedelta(days=5)).isoformat()
    cuerpo["ends_at"] = (ahora + timedelta(days=1)).isoformat()

    respuesta = client.post(RUTA, json=cuerpo, headers=admin)

    assert respuesta.status_code == 409
    assert respuesta.json()["error"]["code"] == "INVALID_PERIOD_RANGE"


@pytest.mark.integration
def test_a_period_cannot_start_and_end_at_the_same_instant(
    client: TestClient, admin: dict[str, str]
) -> None:
    # Una ventana de duración cero no es una ventana.
    momento = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    cuerpo = _cuerpo()
    cuerpo["starts_at"] = momento
    cuerpo["ends_at"] = momento

    assert client.post(RUTA, json=cuerpo, headers=admin).status_code == 409


# ---------------------------------------------------------------------------
# Activación: la operación delicada
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_activating_a_period_opens_it(
    client: TestClient, admin: dict[str, str], db_session: Session
) -> None:
    period_id = _crear(client, admin)

    respuesta = client.put(f"{RUTA}/{period_id}/activate", headers=admin)

    assert respuesta.status_code == 200
    assert respuesta.json()["is_active"] is True


@pytest.mark.integration
def test_activating_a_period_closes_the_previous_one(
    client: TestClient, admin: dict[str, str], db_session: Session
) -> None:
    """El cambio de semestre, que es para lo que existe este endpoint."""
    primero = _crear(client, admin, "2026-1-V1")
    segundo = _crear(client, admin, "2026-1-V2")
    client.put(f"{RUTA}/{primero}/activate", headers=admin)

    client.put(f"{RUTA}/{segundo}/activate", headers=admin)

    db_session.expire_all()
    assert db_session.get(EnrollmentPeriodModel, primero).is_active is False  # type: ignore[union-attr]
    assert db_session.get(EnrollmentPeriodModel, segundo).is_active is True  # type: ignore[union-attr]


@pytest.mark.integration
def test_there_is_never_more_than_one_active_period(
    client: TestClient, admin: dict[str, str], db_session: Session
) -> None:
    """La invariante que el esquema impone y que este endpoint no puede romper.

    Si la activación intentara abrir la nueva antes de cerrar la anterior, el índice único
    parcial rechazaría la escritura y la petición fallaría con un error de clave duplicada. Que
    responda 200 y quede exactamente una activa demuestra que el orden es el correcto.
    """
    identificadores = [_crear(client, admin, f"2026-1-V{n}") for n in range(1, 5)]

    for period_id in identificadores:
        respuesta = client.put(f"{RUTA}/{period_id}/activate", headers=admin)
        assert respuesta.status_code == 200, respuesta.text
        assert _activos(db_session) == 1

    # La última activada es la que queda abierta.
    db_session.expire_all()
    assert db_session.get(EnrollmentPeriodModel, identificadores[-1]).is_active is True  # type: ignore[union-attr]


@pytest.mark.integration
def test_activating_an_already_active_period_is_idempotent(
    client: TestClient, admin: dict[str, str], db_session: Session
) -> None:
    """Activar lo ya activo devuelve la ventana, no un error.

    El estado que se pide ya se cumple. Responder con un error obligaría a quien llama a
    consultar antes para saber si puede llamar, que es justo lo que un `PUT` no debería exigir.
    """
    period_id = _crear(client, admin)
    client.put(f"{RUTA}/{period_id}/activate", headers=admin)

    respuesta = client.put(f"{RUTA}/{period_id}/activate", headers=admin)

    assert respuesta.status_code == 200
    assert respuesta.json()["is_active"] is True
    assert _activos(db_session) == 1


@pytest.mark.integration
def test_activating_a_period_that_does_not_exist_returns_404(
    client: TestClient, admin: dict[str, str]
) -> None:
    respuesta = client.put(f"{RUTA}/{uuid4()}/activate", headers=admin)

    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["code"] == "PERIOD_NOT_FOUND"


@pytest.mark.integration
def test_a_failed_activation_leaves_the_previous_period_open(
    client: TestClient, admin: dict[str, str], db_session: Session
) -> None:
    """La atomicidad, vista desde el fallo.

    Si la transacción no fuera atómica, un error después de desactivar la anterior dejaría el
    sistema **sin ninguna ventana abierta** y la matrícula cerrada para todo el mundo. Aquí el
    fallo ocurre antes de escribir nada, y la ventana en curso sigue abierta.
    """
    activo = _crear(client, admin)
    client.put(f"{RUTA}/{activo}/activate", headers=admin)

    client.put(f"{RUTA}/{uuid4()}/activate", headers=admin)

    db_session.expire_all()
    assert db_session.get(EnrollmentPeriodModel, activo).is_active is True  # type: ignore[union-attr]
    assert _activos(db_session) == 1


@pytest.mark.integration
def test_the_activated_period_becomes_the_current_one(
    client: TestClient, admin: dict[str, str]
) -> None:
    """El efecto que ve el estudiante: `GET /enrollment-periods/current` cambia."""
    period_id = _crear(client, admin, "2026-1-V9")
    client.put(f"{RUTA}/{period_id}/activate", headers=admin)

    cuerpo = client.get("/api/v1/enrollment-periods/current").json()

    assert cuerpo["code"] == "2026-1-V9"
    # Se creó con apertura dentro de un día: está activa pero todavía no abierta. Es un estado
    # coherente, y `is_open` es quien decide si se puede inscribir.
    assert cuerpo["is_active"] is True
    assert cuerpo["is_open"] is False


# ---------------------------------------------------------------------------
# Listado
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_the_listing_returns_the_paginated_envelope(
    client: TestClient, admin: dict[str, str]
) -> None:
    _crear(client, admin, "2026-1-V1")

    cuerpo = client.get(RUTA, headers=admin).json()

    assert set(cuerpo) == {"items", "total", "page", "size"}
    assert cuerpo["total"] >= 1


@pytest.mark.integration
def test_the_listing_carries_consolidated_at(client: TestClient, admin: dict[str, str]) -> None:
    """El listado tiene que decir si el semestre ya se cerró, y faltaba.

    Es el hallazgo #2 de la QA manual. El campo no viajaba en este listado, así que llegaba
    AUSENTE en vez de `null` y la interfaz —que comprobaba `consolidated_at === null`— daba
    falso para TODAS las ventanas: el botón de cerrar el semestre no aparecía nunca y cada una
    anunciaba «Semestre cerrado el Invalid Date».

    El test se escribe sobre la CLAVE y no sobre su valor: lo que fallaba era que la clave no
    estuviera, y un `assert cuerpo[...] is None` habría pasado igual con el campo ausente si se
    hubiera usado `.get()`.
    """
    _crear(client, admin, "2026-1-V1")

    periodo = client.get(RUTA, headers=admin).json()["items"][0]

    assert "consolidated_at" in periodo
    # Recién creada: abierta, y por tanto sin fecha de cierre.
    assert periodo["consolidated_at"] is None


@pytest.mark.integration
def test_the_listing_comes_newest_first(client: TestClient, admin: dict[str, str]) -> None:
    # Quien consulta busca casi siempre la ventana en curso o la siguiente, no la de hace años.
    client.post(RUTA, json=_cuerpo("VIEJA", dias_hasta_apertura=1), headers=admin)
    client.post(RUTA, json=_cuerpo("NUEVA", dias_hasta_apertura=60), headers=admin)

    codigos = [p["code"] for p in client.get(RUTA, headers=admin).json()["items"]]

    assert codigos.index("NUEVA") < codigos.index("VIEJA")


@pytest.mark.integration
def test_the_listing_lets_you_find_the_id_to_activate(
    client: TestClient, admin: dict[str, str]
) -> None:
    """Es la razón de ser del listado.

    Sin él, el único modo de obtener el identificador sería copiarlo de la respuesta de
    creación, lo que obliga a no perderla y deja sin manejar las ventanas creadas antes.
    """
    _crear(client, admin, "2026-2-V1")

    encontrada = next(
        p for p in client.get(RUTA, headers=admin).json()["items"] if p["code"] == "2026-2-V1"
    )
    respuesta = client.put(f"{RUTA}/{encontrada['id']}/activate", headers=admin)

    assert respuesta.status_code == 200


@pytest.mark.integration
def test_the_listing_requires_admin(client: TestClient) -> None:
    assert client.get(RUTA).status_code == 401
