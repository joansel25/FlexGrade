"""Entrypoint de la API REST.

El contenedor arranca la aplicación con `uvicorn app.interfaces.api.main:app`.

Este módulo es el borde más externo de la arquitectura: es el único lugar, junto
con las dependencias de FastAPI, donde se resuelve la configuración concreta y se
ensamblan las piezas. Por eso puede importar de `app.infrastructure`; el dominio
y la aplicación no.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain.exceptions.authentication import (
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTokenError,
    StudentProfileNotFoundError,
)
from app.domain.exceptions.base import DomainError
from app.infrastructure.config.settings import get_settings
from app.interfaces.api.routers import auth, health, students

settings = get_settings()

app = FastAPI(
    title="Sistema de Matrícula Académica",
    description="API de inscripción y gestión académica.",
    version=settings.app_version,
)

# `/health` va en la raíz, fuera de `settings.api_v1_prefix`: lo consumen Docker
# y el ALB, no los clientes de la API.
app.include_router(health.router)

# Los routers de negocio sí se versionan.
app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(students.router, prefix=settings.api_v1_prefix)


# ---------------------------------------------------------------------------
# Traducción de excepciones de dominio a HTTP.
#
# Centralizada aquí a propósito: cada excepción tiene UN único mapeo para toda
# la aplicación. Repetir `try/except` en cada router llevaría a que el mismo
# error respondiera con códigos distintos según el endpoint.
# ---------------------------------------------------------------------------

# Cada excepción del dominio, con su código HTTP y su `error.code` estable.
_MAPEO_ERRORES: dict[type[DomainError], tuple[int, str]] = {
    InvalidCredentialsError: (401, "INVALID_CREDENTIALS"),
    InvalidTokenError: (401, "INVALID_TOKEN"),
    InactiveUserError: (403, "USER_INACTIVE"),
    StudentProfileNotFoundError: (404, "STUDENT_PROFILE_NOT_FOUND"),
}


def _respuesta_error(status_code: int, code: str, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": exc.message, "details": exc.details}},
    )


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    """Traduce cualquier excepción del dominio a la respuesta estándar de error.

    Recorre el mapeo buscando la coincidencia más específica. Una excepción de
    dominio no contemplada devuelve 400 en vez de 500: es un fallo de negocio
    previsible, no un error del servidor.
    """
    for tipo, (status_code, code) in _MAPEO_ERRORES.items():
        if isinstance(exc, tipo):
            return _respuesta_error(status_code, code, exc)

    return _respuesta_error(400, "DOMAIN_ERROR", exc)
