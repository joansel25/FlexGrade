"""Pruebas del guardián de límite de peticiones (sin Redis).

Lo que se comprueba aquí es la LÓGICA de la decisión: a quién se le cuenta, con qué clave, qué
pasa al pasarse y qué pasa cuando el contador no responde. El comportamiento del contador contra
Redis real —la atomicidad y el vencimiento de la ventana— se prueba en integración, que es donde
existe un Redis contra el que fallar.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.application.dtos.auth_dto import TokenPayload, TokenType
from app.domain.value_objects.user_role import UserRole
from app.infrastructure.config.settings import Settings
from app.interfaces.api.dependencies.rate_limit import (
    limitar_admin,
    limitar_catalogo,
    limitar_inscripcion,
    limitar_login,
)
from app.interfaces.api.errors import RateLimitExceededError
from tests.unit.doubles import InMemoryRateLimiter, LimitadorCaido

_MINIMOS = {
    "database_url": "postgresql+psycopg://u:p@h:5432/d",
    "redis_url": "redis://h:6379/0",
    "jwt_secret": "secreto-de-pruebas",
}


def _settings(**extra: object) -> Settings:
    """Configuración con el limitador ENCENDIDO salvo que el test diga lo contrario.

    La suite lo apaga por defecto (`tests/conftest.py`) para que los límites no tumben tests
    que hacen decenas de peticiones seguidas. Aquí hay que volver a encenderlo, y hacerlo
    explícito en el propio constructor es lo que impide que estas pruebas pasen en verde sin
    ejercitar nada el día que alguien cambie el valor por defecto.
    """
    opciones: dict[str, object] = {"rate_limit_enabled": True, **_MINIMOS, **extra}

    return Settings(**opciones)  # type: ignore[arg-type]


class _PeticionFalsa:
    """Lo mínimo de un `Request` que el guardián usa: de dónde viene."""

    def __init__(self, host: str | None) -> None:
        self.client = None if host is None else type("Cliente", (), {"host": host})()


def _usuario(user_id: object = None) -> TokenPayload:
    return TokenPayload(
        user_id=user_id or uuid4(), role=UserRole.STUDENT, token_type=TokenType.ACCESS
    )


@pytest.mark.unit
def test_deja_pasar_hasta_el_limite_y_rechaza_la_siguiente() -> None:
    limiter = InMemoryRateLimiter()
    settings = _settings(rate_limit_login_per_minute=3)
    peticion = _PeticionFalsa("10.0.0.1")

    for _ in range(3):
        limitar_login(peticion, limiter, settings)  # type: ignore[arg-type]

    with pytest.raises(RateLimitExceededError):
        limitar_login(peticion, limiter, settings)  # type: ignore[arg-type]


@pytest.mark.unit
def test_la_ventana_nueva_devuelve_el_presupuesto() -> None:
    """Un límite que no se renueva no es un límite: es un bloqueo permanente."""
    limiter = InMemoryRateLimiter()
    settings = _settings(rate_limit_login_per_minute=1)
    peticion = _PeticionFalsa("10.0.0.1")

    limitar_login(peticion, limiter, settings)  # type: ignore[arg-type]
    limiter.nueva_ventana()

    limitar_login(peticion, limiter, settings)  # type: ignore[arg-type]


@pytest.mark.unit
def test_dos_direcciones_distintas_no_comparten_presupuesto() -> None:
    """Si lo compartieran, una sola persona podría dejar fuera a toda la universidad."""
    limiter = InMemoryRateLimiter()
    settings = _settings(rate_limit_login_per_minute=1)

    limitar_login(_PeticionFalsa("10.0.0.1"), limiter, settings)  # type: ignore[arg-type]
    limitar_login(_PeticionFalsa("10.0.0.2"), limiter, settings)  # type: ignore[arg-type]


@pytest.mark.unit
def test_dos_ambitos_no_comparten_contador() -> None:
    """Consultar mucho el catálogo no puede dejar a nadie sin inscribirse.

    Es el fallo que aparecería si la clave no llevara el ámbito dentro: los dos límites
    escribirían en el mismo contador y el más generoso agotaría al más estricto.
    """
    limiter = InMemoryRateLimiter()
    settings = _settings(rate_limit_catalog_per_minute=1, rate_limit_enrollment_per_minute=1)
    usuario = _usuario()

    limitar_catalogo(_PeticionFalsa("10.0.0.1"), limiter, settings)  # type: ignore[arg-type]
    limitar_inscripcion(usuario, limiter, settings)  # type: ignore[arg-type]

    assert limiter.llamadas[0].startswith("ratelimit:v1:catalogo:")
    assert limiter.llamadas[1].startswith("ratelimit:v1:inscripcion:")


@pytest.mark.unit
def test_la_inscripcion_se_cuenta_por_usuario_y_no_por_direccion() -> None:
    """Una universidad sale a internet por unas pocas IP públicas.

    Contando por dirección, miles de estudiantes compartirían presupuesto y se lo agotarían
    entre personas distintas, justo durante la ventana de matrícula.
    """
    limiter = InMemoryRateLimiter()
    settings = _settings(rate_limit_enrollment_per_minute=1)

    limitar_inscripcion(_usuario(), limiter, settings)  # type: ignore[arg-type]
    limitar_inscripcion(_usuario(), limiter, settings)  # type: ignore[arg-type]

    assert len(set(limiter.llamadas)) == 2


@pytest.mark.unit
def test_el_rechazo_dice_cuanto_esperar_y_que_limite_se_agoto() -> None:
    """«Espera un momento» sin decir cuánto ni de qué obliga a reintentar a ciegas."""
    limiter = InMemoryRateLimiter()
    settings = _settings(rate_limit_admin_per_minute=1)
    usuario = _usuario()

    limitar_admin(usuario, limiter, settings)  # type: ignore[arg-type]

    with pytest.raises(RateLimitExceededError) as error:
        limitar_admin(usuario, limiter, settings)  # type: ignore[arg-type]

    assert error.value.retry_after_seconds == 60
    assert error.value.details["scope"] == "admin"
    assert error.value.details["limit"] == 1


@pytest.mark.unit
def test_con_el_limitador_apagado_no_se_cuenta_nada() -> None:
    """El interruptor existe para apagarlo sin desplegar; tiene que cortar antes de contar."""
    limiter = InMemoryRateLimiter()
    settings = _settings(rate_limit_enabled=False, rate_limit_login_per_minute=1)
    peticion = _PeticionFalsa("10.0.0.1")

    for _ in range(5):
        limitar_login(peticion, limiter, settings)  # type: ignore[arg-type]

    assert limiter.llamadas == []


@pytest.mark.unit
def test_si_el_contador_no_responde_la_peticion_pasa() -> None:
    """La decisión que más incomoda del adaptador, fijada aquí para que nadie la invierta.

    Fallar cerrado convertiría una caída de Redis —un servicio auxiliar— en el rechazo de TODAS
    las peticiones, es decir, en la caída completa de la matrícula.
    """
    settings = _settings(rate_limit_login_per_minute=1)
    peticion = _PeticionFalsa("10.0.0.1")

    for _ in range(10):
        limitar_login(peticion, LimitadorCaido(), settings)  # type: ignore[arg-type]


@pytest.mark.unit
def test_una_peticion_sin_direccion_se_cuenta_igual() -> None:
    """No contarla sería una puerta abierta que solo hay que saber encontrar."""
    limiter = InMemoryRateLimiter()
    settings = _settings(rate_limit_login_per_minute=1)

    limitar_login(_PeticionFalsa(None), limiter, settings)  # type: ignore[arg-type]

    with pytest.raises(RateLimitExceededError):
        limitar_login(_PeticionFalsa(None), limiter, settings)  # type: ignore[arg-type]
