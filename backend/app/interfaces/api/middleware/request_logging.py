"""Middleware que registra una línea por petición.

Es la pieza que hace diagnosticable el sistema en la nube. Con el autoescalado, la petición
lenta que alguien reporta ocurrió en una instancia que quizá ya no existe: lo único que queda
es lo que se escribió en Azure Monitor mientras ocurría.

Cada línea lleva el identificador de la petición, y ese identificador viaja también en la
respuesta (`X-Request-ID`). Cuando un estudiante dice «me falló la inscripción», con ese valor
se encuentra en Log Analytics la línea exacta, entre millones, sin buscar por hora aproximada.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = logging.getLogger("app.request")

# Cabeceras de traza que la petición puede traer ya puesta desde el borde de la red. Se
# reutiliza la primera que llegue como identificador: así la línea de la aplicación y la del
# servicio de delante hablan del MISMO viaje, que es lo que permite saber si el tiempo se fue
# en la red o dentro del proceso.
#
# El orden importa y es de FUERA hacia dentro. `X-Azure-Ref` la pone Azure Front Door, que es
# el primero que toca la petición y el único valor que aparece en SUS registros: si se
# prefiriera `traceparent`, buscar en Front Door por el identificador que reportó el
# estudiante no encontraría nada. `traceparent` es el estándar W3C que usa Application
# Insights y cubre lo que entra sin pasar por el borde.
_CABECERAS_TRAZA = ("x-azure-ref", "traceparent")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Registra método, ruta, código y duración de cada petición."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = next(
            (valor for cabecera in _CABECERAS_TRAZA if (valor := request.headers.get(cabecera))),
            None,
        ) or str(uuid.uuid4())
        # `perf_counter` y no `time()`: mide un intervalo y no le afecta un ajuste de reloj
        # del sistema, que en una medición de milisegundos daría duraciones negativas.
        inicio = time.perf_counter()

        try:
            respuesta = await call_next(request)
        except Exception:
            duracion_ms = round((time.perf_counter() - inicio) * 1000, 2)
            # Se registra ANTES de propagar: si no, el fallo llegaría a Azure Monitor como un 500
            # de uvicorn sin ruta, sin duración y sin identificador con el que rastrearlo.
            logger.exception(
                f"{request.method} {request.url.path} -> excepcion no controlada "
                f"({duracion_ms} ms)",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duracion_ms,
                },
            )
            raise

        duracion_ms = round((time.perf_counter() - inicio) * 1000, 2)

        logger.info(
            # El mensaje resume la línea para quien la lee en la terminal durante el
            # desarrollo; los campos de abajo son los que consulta CloudWatch.
            f"{request.method} {request.url.path} -> {respuesta.status_code} "
            f"({duracion_ms} ms)",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": respuesta.status_code,
                "duration_ms": duracion_ms,
                # IP real del estudiante, no la del balanceador: uvicorn la resuelve desde
                # `X-Forwarded-For` porque el contenedor arranca con `--proxy-headers`.
                "client_ip": request.client.host if request.client else None,
            },
        )

        respuesta.headers["X-Request-ID"] = request_id

        return respuesta
