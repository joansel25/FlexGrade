"""Guardianes de límite de peticiones.

Se declaran **una vez por router**, igual que `require_admin`, y por la misma razón: repetirlos
endpoint por endpoint garantiza que un día se añada uno nuevo y nadie se acuerde de ponerlo.
La excepción es el inicio de sesión, que lleva el suyo propio en el endpoint —no en el router—
porque `/auth/refresh` comparte prefijo y con un límite de cinco por minuto una sesión que se
renueva sola acabaría gastándose el presupuesto del inicio de sesión.

**Por quién se cuenta, y por qué no siempre igual.**

- **Inicio de sesión: por IP.** No hay usuario todavía; ese es justo el punto. Lo que se frena
  es probar contraseñas.
- **Catálogo: por IP.** `GET /courses` es público y se consulta sin token, así que no hay
  usuario por el que contar. `API.md` decía «por usuario» y se corrigió: era una contradicción
  con el propio contrato del endpoint.
- **Inscripción y administración: por usuario.** Ahí siempre hay token, y contar por usuario es
  más justo y más preciso: una universidad sale a internet por unas pocas IP públicas, así que
  contar por IP dejaría a miles de estudiantes compartiendo un mismo presupuesto y agotándolo
  entre personas distintas.

**La IP real depende de una opción de arranque.** Detrás del Application Gateway, todas las
peticiones llegan desde una dirección interna; `request.client.host` solo trae la del estudiante
porque uvicorn corre con `--proxy-headers` y lee `X-Forwarded-For` (ver el `CMD` del
`Dockerfile`). Sin esa opción, los límites por IP se aplicarían a TODO EL MUNDO A LA VEZ, como
si fueran una sola persona: el sistema entero se quedaría con cinco inicios de sesión por
minuto.
"""

from __future__ import annotations

from fastapi import Depends, Request

from app.application.ports.rate_limiter import RateLimiter
from app.infrastructure.config.settings import Settings
from app.interfaces.api.dependencies.auth import CurrentUserDep
from app.interfaces.api.dependencies.di import RateLimiterDep, SettingsDep
from app.interfaces.api.errors import RateLimitExceededError

# Los límites de `API.md` son por minuto. La ventana se declara aquí una vez para que el número
# de la configuración y el periodo al que se refiere no puedan separarse.
_VENTANA_SEGUNDOS = 60

_MENSAJES = {
    "login": "Demasiados intentos de inicio de sesión. Espera un momento y vuelve a intentarlo.",
    "catalogo": "Demasiadas consultas al catálogo. Espera un momento y vuelve a intentarlo.",
    "inscripcion": (
        "Demasiadas operaciones de inscripción seguidas. "
        "Espera un momento y vuelve a intentarlo."
    ),
    "admin": "Demasiadas peticiones de administración. Espera un momento y vuelve a intentarlo.",
}


def _aplicar(
    limiter: RateLimiter,
    settings: Settings,
    *,
    ambito: str,
    identidad: str,
    limite: int,
) -> None:
    """Cuenta la petición y la rechaza si se pasó del límite.

    El ámbito viaja DENTRO de la clave. Sin él, un estudiante que consulta mucho el catálogo se
    quedaría también sin inscripciones, porque las dos cosas compartirían contador.

    Args:
        limiter: el contador.
        settings: configuración, para el interruptor general.
        ambito: cuál de los cuatro límites se está aplicando.
        identidad: quién se está limitando (`ip:...` o `user:...`).
        limite: peticiones permitidas por minuto.

    Raises:
        RateLimitExceededError: si la petición no cabe en la ventana.
    """
    if not settings.rate_limit_enabled:
        return

    resultado = limiter.hit(
        f"ratelimit:v1:{ambito}:{identidad}",
        limit=limite,
        window_seconds=_VENTANA_SEGUNDOS,
    )

    if resultado.allowed:
        return

    raise RateLimitExceededError(
        message=_MENSAJES[ambito],
        retry_after_seconds=resultado.retry_after_seconds,
        # El ámbito va en los `details` para que el cliente sepa CUÁL de los cuatro límites se
        # agotó: «espera un momento» sin decir para qué deja a quien administra sin saber si
        # puede seguir consultando el catálogo mientras tanto.
        details={"scope": ambito, "limit": limite, "window_seconds": _VENTANA_SEGUNDOS},
    )


def _identidad_por_ip(request: Request) -> str:
    # `request.client` es `None` en transportes sin dirección —tests con ASGI en memoria, un
    # socket unix—. Se agrupan bajo una identidad común en vez de dejar pasar sin contar: lo
    # contrario sería una puerta abierta que solo hay que saber encontrar.
    host = request.client.host if request.client else "desconocido"
    return f"ip:{host}"


def limitar_login(request: Request, limiter: RateLimiterDep, settings: SettingsDep) -> None:
    """Frena los intentos de inicio de sesión desde una misma dirección."""
    _aplicar(
        limiter,
        settings,
        ambito="login",
        identidad=_identidad_por_ip(request),
        limite=settings.rate_limit_login_per_minute,
    )


def limitar_catalogo(request: Request, limiter: RateLimiterDep, settings: SettingsDep) -> None:
    """Frena las consultas al catálogo desde una misma dirección."""
    _aplicar(
        limiter,
        settings,
        ambito="catalogo",
        identidad=_identidad_por_ip(request),
        limite=settings.rate_limit_catalog_per_minute,
    )


def limitar_inscripcion(
    usuario: CurrentUserDep, limiter: RateLimiterDep, settings: SettingsDep
) -> None:
    """Frena las operaciones de inscripción de un mismo usuario.

    Depende de `CurrentUserDep`, así que una petición sin token falla antes con `401
    MISSING_TOKEN` y ni siquiera llega a contarse. Es lo correcto: sin token no hay a quién
    contarle nada, y responder 429 a quien no se ha autenticado escondería el error real.
    """
    _aplicar(
        limiter,
        settings,
        ambito="inscripcion",
        identidad=f"user:{usuario.user_id}",
        limite=settings.rate_limit_enrollment_per_minute,
    )


def limitar_admin(usuario: CurrentUserDep, limiter: RateLimiterDep, settings: SettingsDep) -> None:
    """Frena las peticiones de administración de un mismo usuario."""
    _aplicar(
        limiter,
        settings,
        ambito="admin",
        identidad=f"user:{usuario.user_id}",
        limite=settings.rate_limit_admin_per_minute,
    )


# Envoltorios listos para `dependencies=[...]` de un router. Se exponen así, y no como el
# `Depends` suelto en cada archivo, para que añadir un router nuevo sea elegir un límite de
# esta lista en vez de escribir la llamada otra vez.
# Sin anotar a propósito: el tipo lo infiere mypy de `Depends`, y escribirlo a mano lo
# convertía en `Callable[..., object]`, que es lo que `dependencies=[...]` NO acepta.
LimiteLogin = Depends(limitar_login)
LimiteCatalogo = Depends(limitar_catalogo)
LimiteInscripcion = Depends(limitar_inscripcion)
LimiteAdmin = Depends(limitar_admin)
