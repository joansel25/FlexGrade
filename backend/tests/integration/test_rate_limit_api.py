"""Pruebas del límite de peticiones contra Redis y la API reales.

Los unitarios comprueban la lógica de la decisión. Aquí se comprueba lo que solo existe cuando
hay un Redis de verdad y una aplicación montada: que el contador vive FUERA del proceso, que la
respuesta lleva el formato de error del proyecto con su `Retry-After`, que el límite está
declarado en los routers que deben tenerlo, y —lo más fácil de romper sin enterarse— que NO está
declarado en el que no debe tenerlo.

La suite corre con el limitador apagado (`tests/conftest.py`), así que estos tests lo encienden
con números pequeños mediante `dependency_overrides`, que es el mecanismo de FastAPI para
sustituir una dependencia en una aplicación ya montada.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.cache.client import get_redis_client
from app.infrastructure.config.settings import Settings, get_settings
from app.interfaces.api.main import app

# Números pequeños para poder agotarlos en un bucle corto. Los reales viven en `API.md`; lo que
# se prueba aquí es el mecanismo, no la cifra.
_LOGIN = 2
_CATALOGO = 3


def _limpiar_contadores() -> None:
    cliente = get_redis_client()
    claves = list(cliente.scan_iter("ratelimit:v1:*"))

    if claves:
        cliente.delete(*claves)


@pytest.fixture
def limitador_encendido() -> Iterator[None]:
    """Enciende el limitador durante el test y deja Redis sin contadores al terminar.

    Limpiar las claves no es cortesía: la ventana dura un minuto REAL, así que sin borrarlas el
    siguiente test heredaría el contador agotado del anterior y fallaría por algo que no tiene
    nada que ver con lo que comprueba. Es el mismo tipo de contaminación entre tests que la
    sección 1 de la memoria del proyecto advierte para la base de datos.
    """
    ajustado = Settings(
        **{
            **get_settings().model_dump(),
            "rate_limit_enabled": True,
            "rate_limit_login_per_minute": _LOGIN,
            "rate_limit_catalog_per_minute": _CATALOGO,
        }
    )

    app.dependency_overrides[get_settings] = lambda: ajustado
    _limpiar_contadores()

    try:
        yield
    finally:
        app.dependency_overrides.pop(get_settings, None)
        _limpiar_contadores()


@pytest.mark.integration
def test_el_login_se_corta_al_pasar_del_limite(
    client: TestClient, limitador_encendido: None
) -> None:
    """Las credenciales son inválidas a propósito: lo que se frena es PROBAR contraseñas.

    Si el contador solo subiera con los intentos correctos, no protegería de nada: la fuerza
    bruta consiste precisamente en fallar muchas veces.
    """
    credenciales = {"email": "quien@sea.edu.co", "password": "loQueSea123"}

    for _ in range(_LOGIN):
        assert client.post("/api/v1/auth/login", json=credenciales).status_code == 401

    respuesta = client.post("/api/v1/auth/login", json=credenciales)

    assert respuesta.status_code == 429


@pytest.mark.integration
def test_el_rechazo_usa_el_sobre_de_error_del_proyecto(
    client: TestClient, limitador_encendido: None
) -> None:
    """Un 429 con otro formato obligaría al cliente a distinguir dos formas de error."""
    credenciales = {"email": "quien@sea.edu.co", "password": "loQueSea123"}

    for _ in range(_LOGIN + 1):
        respuesta = client.post("/api/v1/auth/login", json=credenciales)

    cuerpo = respuesta.json()

    assert respuesta.status_code == 429
    assert cuerpo["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert cuerpo["error"]["details"]["scope"] == "login"
    assert cuerpo["error"]["details"]["limit"] == _LOGIN


@pytest.mark.integration
def test_el_rechazo_dice_cuando_volver_a_intentarlo(
    client: TestClient, limitador_encendido: None
) -> None:
    """Sin `Retry-After`, un cliente rechazado solo puede reintentar a ciegas.

    Durante la ventana de matrícula eso significa reintentar en bucle y empeorar exactamente la
    situación que el límite existe para contener.
    """
    credenciales = {"email": "quien@sea.edu.co", "password": "loQueSea123"}

    for _ in range(_LOGIN + 1):
        respuesta = client.post("/api/v1/auth/login", json=credenciales)

    espera = int(respuesta.headers["Retry-After"])

    assert 0 < espera <= 60


@pytest.mark.integration
def test_el_catalogo_tiene_su_propio_presupuesto(
    client: TestClient, limitador_encendido: None
) -> None:
    """Consultar mucho el catálogo no puede dejar a nadie sin poder iniciar sesión.

    Es el fallo que aparecería si la clave no llevara el ámbito dentro: los dos límites
    escribirían en el mismo contador aunque se cuenten por la misma dirección.
    """
    for _ in range(_CATALOGO):
        assert client.get("/api/v1/courses").status_code == 200

    assert client.get("/api/v1/courses").status_code == 429
    # El presupuesto del login sigue intacto: distinto ámbito, distinto contador.
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "quien@sea.edu.co", "password": "loQueSea123"}
        ).status_code
        == 401
    )


@pytest.mark.integration
def test_el_contador_vive_en_redis_y_no_en_el_proceso(
    client: TestClient, limitador_encendido: None
) -> None:
    """Es lo que hace que el límite signifique algo con varias instancias.

    Con un contador en memoria, cada proceso llevaría su propia cuenta y el límite real sería el
    declarado multiplicado por un número de instancias que además cambia solo con el
    autoescalado. Un límite que depende de a qué instancia te toque llegar no es un límite.
    """
    client.get("/api/v1/courses")

    cliente_redis = get_redis_client()
    claves = list(cliente_redis.scan_iter("ratelimit:v1:catalogo:*"))

    assert len(claves) == 1
    # Con vencimiento: sin él, la clave se quedaría para siempre y ese cliente estaría
    # bloqueado sin más síntoma que un 429 eterno que nadie sabría explicar.
    assert 0 < cliente_redis.ttl(claves[0]) <= 60


@pytest.mark.integration
def test_health_no_esta_limitado(client: TestClient, limitador_encendido: None) -> None:
    """El Application Gateway sondea `/health` cada pocos segundos, sin descanso.

    Con un límite encima, la sonda acabaría recibiendo 429, el balanceador daría la instancia
    por caída y la retiraría del servicio: el limitador tumbaría la aplicación que protege. Por
    eso este test existe aunque hoy no haya límite ahí — lo que fija es que no se le ponga.
    """
    for _ in range(_CATALOGO + 5):
        assert client.get("/health").status_code == 200
