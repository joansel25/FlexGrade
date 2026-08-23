"""Prueba de integración del flujo completo: login -> endpoint protegido.

Es el criterio de "terminado" de la Fase 1 (DEVELOPMENT_WORKFLOW.md): un
estudiante se autentica y consulta su perfil. Recorre las cuatro capas con
PostgreSQL real detrás: router -> caso de uso -> repositorio -> base de datos.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

RUTA_LOGIN = "/api/v1/auth/login"
RUTA_REFRESH = "/api/v1/auth/refresh"
RUTA_LOGOUT = "/api/v1/auth/logout"
RUTA_PERFIL = "/api/v1/students/me"


def _iniciar_sesion(client: TestClient, credenciales: dict[str, str]) -> dict[str, str]:
    respuesta = client.post(
        RUTA_LOGIN,
        json={"email": credenciales["email"], "password": credenciales["password"]},
    )
    assert respuesta.status_code == 200, respuesta.text
    return dict(respuesta.json())


@pytest.mark.integration
def test_login_when_credentials_are_valid_returns_200(
    client: TestClient, estudiante_registrado: dict[str, str]
) -> None:
    respuesta = client.post(
        RUTA_LOGIN,
        json={
            "email": estudiante_registrado["email"],
            "password": estudiante_registrado["password"],
        },
    )

    assert respuesta.status_code == 200


@pytest.mark.integration
def test_login_when_credentials_are_valid_returns_an_access_token(
    client: TestClient, estudiante_registrado: dict[str, str]
) -> None:
    assert _iniciar_sesion(client, estudiante_registrado)["access_token"]


@pytest.mark.integration
def test_login_when_password_is_wrong_returns_401(
    client: TestClient, estudiante_registrado: dict[str, str]
) -> None:
    respuesta = client.post(
        RUTA_LOGIN,
        json={"email": estudiante_registrado["email"], "password": "ClaveEquivocada"},
    )

    assert respuesta.status_code == 401


@pytest.mark.integration
def test_login_when_password_is_wrong_returns_the_documented_error_code(
    client: TestClient, estudiante_registrado: dict[str, str]
) -> None:
    respuesta = client.post(
        RUTA_LOGIN,
        json={"email": estudiante_registrado["email"], "password": "ClaveEquivocada"},
    )

    assert respuesta.json()["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.integration
def test_profile_when_token_is_valid_returns_200(
    client: TestClient, estudiante_registrado: dict[str, str]
) -> None:
    tokens = _iniciar_sesion(client, estudiante_registrado)

    respuesta = client.get(
        RUTA_PERFIL, headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )

    assert respuesta.status_code == 200


@pytest.mark.integration
def test_profile_when_token_is_valid_returns_the_own_student_code(
    client: TestClient, estudiante_registrado: dict[str, str]
) -> None:
    tokens = _iniciar_sesion(client, estudiante_registrado)

    respuesta = client.get(
        RUTA_PERFIL, headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )

    assert respuesta.json()["student_code"] == estudiante_registrado["student_code"]


@pytest.mark.integration
def test_profile_when_no_token_is_sent_returns_401(client: TestClient) -> None:
    assert client.get(RUTA_PERFIL).status_code == 401


@pytest.mark.integration
def test_profile_when_token_is_invalid_returns_401(client: TestClient) -> None:
    respuesta = client.get(RUTA_PERFIL, headers={"Authorization": "Bearer token-falsificado"})

    assert respuesta.status_code == 401


@pytest.mark.integration
def test_profile_when_refresh_token_used_as_access_returns_401(
    client: TestClient, estudiante_registrado: dict[str, str]
) -> None:
    # El refresh token dura 7 días: si sirviera para llamar a la API, la vida
    # corta del access token no protegería de nada.
    tokens = _iniciar_sesion(client, estudiante_registrado)

    respuesta = client.get(
        RUTA_PERFIL, headers={"Authorization": f"Bearer {tokens['refresh_token']}"}
    )

    assert respuesta.status_code == 401


@pytest.mark.integration
def test_refresh_when_token_is_valid_returns_a_usable_access_token(
    client: TestClient, estudiante_registrado: dict[str, str]
) -> None:
    tokens = _iniciar_sesion(client, estudiante_registrado)

    renovado = client.post(RUTA_REFRESH, json={"refresh_token": tokens["refresh_token"]})
    perfil = client.get(
        RUTA_PERFIL,
        headers={"Authorization": f"Bearer {renovado.json()['access_token']}"},
    )

    assert perfil.status_code == 200


@pytest.mark.integration
def test_logout_when_token_is_valid_returns_204(
    client: TestClient, estudiante_registrado: dict[str, str]
) -> None:
    tokens = _iniciar_sesion(client, estudiante_registrado)

    respuesta = client.post(
        RUTA_LOGOUT, headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )

    assert respuesta.status_code == 204


@pytest.mark.integration
def test_logout_when_no_token_is_sent_returns_401(client: TestClient) -> None:
    assert client.post(RUTA_LOGOUT).status_code == 401


@pytest.mark.integration
def test_profile_returns_the_nested_program_block(
    client: TestClient, estudiante_registrado: dict[str, str]
) -> None:
    """Cierre de la divergencia que la Fase 1 dejo documentada en API.md.

    Aquel `program_id` plano existia solo porque no habia repositorio de programas. Ahora que
    lo hay, la respuesta cumple el contrato: un bloque `program` con codigo y nombre, para que
    el frontend no tenga que hacer una segunda llamada solo para mostrar la carrera.
    """
    tokens = _iniciar_sesion(client, estudiante_registrado)

    cuerpo = client.get(
        RUTA_PERFIL, headers={"Authorization": f"Bearer {tokens['access_token']}"}
    ).json()

    assert cuerpo["program"]["code"] == estudiante_registrado["program_code"]
    assert cuerpo["program"]["name"] == estudiante_registrado["program_name"]
    assert "program_id" not in cuerpo
