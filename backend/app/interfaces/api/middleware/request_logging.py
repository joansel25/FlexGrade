"""Middleware que registra una línea por petición.

Es la pieza que hace diagnosticable el sistema en la nube. Con el autoescalado, la petición
lenta que alguien reporta ocurrió en una instancia que quizá ya no existe: lo único que queda
es lo que se escribió en CloudWatch mientras ocurría.

Cada línea lleva el identificador de la petición, y ese identificador viaja también en la
respuesta (`X-Request-ID`). Cuando un estudiante dice «me falló la inscripción», con ese valor
se encuentra en Insights la línea exacta, entre millones, sin buscar por hora aproximada.
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

# Cabecera que el ALB añade a cada petición. Se reutiliza como identificador cuando está
# presente: así la línea de la aplicación y la del balanceador hablan del MISMO viaje, que es
# lo que permite saber si el tiempo se fue en la red o dentro del proceso.
_CABECERA_TRAZA = "x-amzn-trace-id"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Registra método, ruta, código y duración de cada petición."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(_CABECERA_TRAZA) or str(uuid.uuid4())
        # `perf_counter` y no `time()`: mide un intervalo y no le afecta un ajuste de reloj
        # del sistema, que en una medición de milisegundos daría duraciones negativas.
        inicio = time.perf_counter()

        try:
            respuesta = await call_next(request)
        except Exception:
            duracion_ms = round((time.perf_counter() - inicio) * 1000, 2)
            # Se registra ANTES de propagar: si no, el fallo llegaría a CloudWatch como un 500
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
