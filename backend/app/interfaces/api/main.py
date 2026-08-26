"""Entrypoint de la API REST.

El contenedor arranca la aplicación con `uvicorn app.interfaces.api.main:app`.

Este módulo es el borde más externo de la arquitectura: es el único lugar, junto
con las dependencias de FastAPI, donde se resuelve la configuración concreta y se
ensamblan las piezas. Por eso puede importar de `app.infrastructure`; el dominio
y la aplicación no.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.domain.exceptions.admin import (
    CapacityBelowEnrolledError,
    ConcurrentOfferingUpdateError,
    CourseRequiredByOthersError,
    DuplicateCourseCodeError,
    DuplicateOfferingGroupError,
    DuplicatePeriodCodeError,
    DuplicateSpaceCodeError,
    InvalidPeriodRangeError,
    OverlappingScheduleError,
    SpaceCapacityExceededError,
    SpaceDoubleBookedError,
)
from app.domain.exceptions.authentication import (
    AdminRequiredError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTokenError,
    MissingTokenError,
    StudentProfileNotFoundError,
)
from app.domain.exceptions.base import DomainError
from app.domain.exceptions.catalog import (
    CourseNotFoundError,
    NoActivePeriodError,
    OfferingNotFoundError,
    PeriodNotFoundError,
    ProfessorNotFoundError,
    ProgramNotFoundError,
    SpaceNotFoundError,
)
from app.domain.exceptions.enrollment import (
    AlreadyEnrolledError,
    CapacityExceededError,
    CorequisiteDependencyError,
    CorequisitesNotMetError,
    CourseNotInProgramError,
    EnrollmentAlreadyCancelledError,
    EnrollmentNotFoundError,
    EnrollmentPeriodInactiveError,
    PrerequisitesNotMetError,
    ScheduleConflictError,
)
from app.domain.exceptions.invalid_value import InvalidScheduleBlockError
from app.infrastructure.config.settings import get_settings
from app.infrastructure.logging.setup import configurar_logging
from app.interfaces.api.middleware.request_logging import RequestLoggingMiddleware
from app.interfaces.api.routers import (
    admin,
    auth,
    courses,
    enrollments,
    health,
    offerings,
    periods,
    students,
)

settings = get_settings()

# Antes de construir la aplicación: uvicorn instala sus manejadores al arrancar y hay que
# reemplazarlos, no sumarse a ellos. En la nube el formato es JSON porque quien lee estas
# líneas es CloudWatch Logs Insights, no una persona con la terminal abierta.
configurar_logging(level=settings.log_level, json_format=settings.environment != "dev")

app = FastAPI(
    title="Sistema de Matrícula Académica",
    description="API de inscripción y gestión académica.",
    version=settings.app_version,
    # La documentación interactiva se puede apagar por variable de entorno, sin reconstruir la
    # imagen. Expone el mapa completo de la API, incluidos los endpoints de administración.
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)

# ---------------------------------------------------------------------------
# Middleware. El orden de registro es el inverso al de ejecución: lo último que se añade es lo
# primero que ve la petición. El registro va el último a propósito, para que su medición de
# duración incluya el trabajo de todo lo demás.
# ---------------------------------------------------------------------------

# CORS. En local el frontend y la API comparten `localhost`; en la nube NO: el frontend se
# sirve desde CloudFront y la API desde el balanceador, que son dominios distintos. Sin esta
# lista el navegador bloquea cada llamada del estudiante y la API parece caída aunque responda.
#
# Se declaran los orígenes exactos, nunca `*`: con `allow_credentials=True` el comodín ni
# siquiera es válido, y una API de matrícula no debe aceptar peticiones desde cualquier sitio.
if settings.cors_allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        # El navegador guarda la respuesta del `preflight` diez minutos en vez de preguntar
        # antes de cada llamada: durante la matrícula eso es la mitad de las peticiones.
        max_age=600,
    )

app.add_middleware(RequestLoggingMiddleware)

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
app.include_router(admin.router, prefix=settings.api_v1_prefix)


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
    MissingTokenError: (401, "MISSING_TOKEN"),
    InvalidTokenError: (401, "INVALID_TOKEN"),
    InactiveUserError: (403, "USER_INACTIVE"),
    AdminRequiredError: (403, "ADMIN_REQUIRED"),
    StudentProfileNotFoundError: (404, "STUDENT_PROFILE_NOT_FOUND"),
    # Catálogo académico (Fase 2). Se registran junto a las excepciones, no junto a los
    # endpoints que las lanzan: una excepción de dominio sin entrada aquí cae en el 400
    # genérico del final, y "la materia no existe" respondería 400 en vez de 404 sin que
    # nada fallara de forma visible.
    CourseNotFoundError: (404, "COURSE_NOT_FOUND"),
    OfferingNotFoundError: (404, "OFFERING_NOT_FOUND"),
    NoActivePeriodError: (404, "NO_ACTIVE_PERIOD"),
    PeriodNotFoundError: (404, "PERIOD_NOT_FOUND"),
    ProfessorNotFoundError: (404, "PROFESSOR_NOT_FOUND"),
    ProgramNotFoundError: (404, "PROGRAM_NOT_FOUND"),
    # 400 y no 409: la franja pedida está MAL FORMADA —«de 12 a 10», un día fuera de rango—, no
    # es un conflicto con el estado del sistema. Registrarla aquí evita que caiga en el
    # `DOMAIN_ERROR` genérico del final, donde el cliente no puede distinguirla de nada más.
    InvalidScheduleBlockError: (400, "INVALID_SCHEDULE_BLOCK"),
    SpaceNotFoundError: (404, "SPACE_NOT_FOUND"),
    # Inscripción (Fase 3), con los códigos que fija `API.md` sección 4.
    #
    # Casi todos son 409 y no 400: la petición está bien formada y el cliente tiene permiso;
    # lo que impide la operación es el ESTADO del sistema. El mismo cuerpo enviado cinco
    # minutos antes habría funcionado.
    EnrollmentPeriodInactiveError: (409, "ENROLLMENT_PERIOD_INACTIVE"),
    CapacityExceededError: (409, "COURSE_CAPACITY_EXCEEDED"),
    AlreadyEnrolledError: (409, "ALREADY_ENROLLED"),
    PrerequisitesNotMetError: (409, "PREREQUISITES_NOT_MET"),
    CorequisitesNotMetError: (409, "COREQUISITES_NOT_MET"),
    # La cara inversa: cancelar dejaría inscrita una materia sin el correquisito que
    # exige. Es un conflicto de estado y no un 403, porque cancelar la otra materia
    # primero hace que la misma petición funcione.
    CorequisiteDependencyError: (409, "COREQUISITE_DEPENDENCY"),
    ScheduleConflictError: (409, "SCHEDULE_CONFLICT"),
    EnrollmentAlreadyCancelledError: (409, "ENROLLMENT_ALREADY_CANCELLED"),
    # La excepción: no es un conflicto de estado sino una operación que a esta persona no le
    # corresponde hacer.
    CourseNotInProgramError: (403, "COURSE_NOT_IN_PROGRAM"),
    EnrollmentNotFoundError: (404, "ENROLLMENT_NOT_FOUND"),
    # Administración (Fase 4). Son 409 por la misma razón: la petición está bien formada y
    # quien la envía tiene permiso; lo que impide la operación es el estado del sistema.
    DuplicatePeriodCodeError: (409, "DUPLICATE_PERIOD_CODE"),
    InvalidPeriodRangeError: (409, "INVALID_PERIOD_RANGE"),
    DuplicateCourseCodeError: (409, "DUPLICATE_COURSE_CODE"),
    DuplicateOfferingGroupError: (409, "DUPLICATE_OFFERING_GROUP"),
    CapacityBelowEnrolledError: (409, "CAPACITY_BELOW_ENROLLED"),
    OverlappingScheduleError: (409, "OVERLAPPING_SCHEDULE"),
    # Fase 7. Son 409 por la misma razón que el resto: la petición está bien formada y
    # quien la envía tiene permiso; lo que impide la operación es el estado del sistema.
    SpaceDoubleBookedError: (409, "SPACE_DOUBLE_BOOKED"),
    SpaceCapacityExceededError: (409, "SPACE_CAPACITY_EXCEEDED"),
    # Fase 8. Conflictos de estado al editar el catálogo y los planes.
    DuplicateSpaceCodeError: (409, "DUPLICATE_SPACE_CODE"),
    CourseRequiredByOthersError: (409, "COURSE_REQUIRED_BY_OTHERS"),
    # 409 y no 500: la escritura no se aplicó porque otra ganó la carrera, y repetir la misma
    # petición tiene todas las papeletas de funcionar. Un 500 diría que el servidor falló, que
    # es exactamente lo que no ocurrió.
    ConcurrentOfferingUpdateError: (409, "CONCURRENT_MODIFICATION"),
}


def _respuesta_error(status_code: int, code: str, exc: DomainError) -> JSONResponse:
    # `WWW-Authenticate` acompaña a todo 401: es lo que dice el estándar HTTP y lo que permite
    # a un cliente saber CÓMO autenticarse. La ponía el guard cuando lanzaba `HTTPException`
    # directamente; al centralizar el formato de error aquí, la cabecera se centraliza con él.
    cabeceras = {"WWW-Authenticate": "Bearer"} if status_code == 401 else None

    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": exc.message, "details": exc.details}},
        headers=cabeceras,
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
