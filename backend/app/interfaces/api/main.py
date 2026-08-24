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
from app.domain.exceptions.catalog import (
    CourseNotFoundError,
    NoActivePeriodError,
    OfferingNotFoundError,
)
from app.domain.exceptions.enrollment import (
    AlreadyEnrolledError,
    CapacityExceededError,
    CourseNotInProgramError,
    EnrollmentAlreadyCancelledError,
    EnrollmentNotFoundError,
    EnrollmentPeriodInactiveError,
    PrerequisitesNotMetError,
    ScheduleConflictError,
)
from app.infrastructure.config.settings import get_settings
from app.interfaces.api.routers import (
    auth,
    courses,
    enrollments,
    health,
    offerings,
    periods,
    students,
)

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
app.include_router(courses.router, prefix=settings.api_v1_prefix)
app.include_router(offerings.router, prefix=settings.api_v1_prefix)
app.include_router(periods.router, prefix=settings.api_v1_prefix)
app.include_router(enrollments.router, prefix=settings.api_v1_prefix)


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
    # Catálogo académico (Fase 2). Se registran junto a las excepciones, no junto a los
    # endpoints que las lanzan: una excepción de dominio sin entrada aquí cae en el 400
    # genérico del final, y "la materia no existe" respondería 400 en vez de 404 sin que
    # nada fallara de forma visible.
    CourseNotFoundError: (404, "COURSE_NOT_FOUND"),
    OfferingNotFoundError: (404, "OFFERING_NOT_FOUND"),
    NoActivePeriodError: (404, "NO_ACTIVE_PERIOD"),
    # Inscripción (Fase 3), con los códigos que fija `API.md` sección 4.
    #
    # Casi todos son 409 y no 400: la petición está bien formada y el cliente tiene permiso;
    # lo que impide la operación es el ESTADO del sistema. El mismo cuerpo enviado cinco
    # minutos antes habría funcionado.
    EnrollmentPeriodInactiveError: (409, "ENROLLMENT_PERIOD_INACTIVE"),
    CapacityExceededError: (409, "COURSE_CAPACITY_EXCEEDED"),
    AlreadyEnrolledError: (409, "ALREADY_ENROLLED"),
    PrerequisitesNotMetError: (409, "PREREQUISITES_NOT_MET"),
    ScheduleConflictError: (409, "SCHEDULE_CONFLICT"),
    EnrollmentAlreadyCancelledError: (409, "ENROLLMENT_ALREADY_CANCELLED"),
    # La excepción: no es un conflicto de estado sino una operación que a esta persona no le
    # corresponde hacer.
    CourseNotInProgramError: (403, "COURSE_NOT_IN_PROGRAM"),
    EnrollmentNotFoundError: (404, "ENROLLMENT_NOT_FOUND"),
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
