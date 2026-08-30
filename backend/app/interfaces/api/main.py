"""Entrypoint de la API REST.

El contenedor arranca la aplicación con `uvicorn app.interfaces.api.main:app`.

Este módulo es el borde más externo de la arquitectura: es el único lugar, junto
con las dependencias de FastAPI, donde se resuelve la configuración concreta y se
ensamblan las piezas. Por eso puede importar de `app.infrastructure`; el dominio
y la aplicación no.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.domain.exceptions.admin import (
    AlreadyInAcademicHistoryError,
    CapacityBelowEnrolledError,
    ConcurrentOfferingUpdateError,
    CourseRequiredByOthersError,
    DuplicateCourseCodeError,
    DuplicateOfferingGroupError,
    DuplicatePeriodCodeError,
    DuplicateSpaceCodeError,
    ImpossibleRequirementCycleError,
    InconsistentConsolidationError,
    InvalidPeriodRangeError,
    OverlappingScheduleError,
    PeriodAlreadyConsolidatedError,
    PeriodHasUngradedEnrollmentsError,
    PeriodStillOpenError,
    RequirementWouldTrapEnrolledError,
    SpaceCapacityExceededError,
    SpaceDoubleBookedError,
)
from app.domain.exceptions.authentication import (
    AdminRequiredError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTokenError,
    MissingTokenError,
    ProfessorProfileNotFoundError,
    ProfessorRequiredError,
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
    AlreadyEnrolledInCourseError,
    CannotGradeCancelledEnrollmentError,
    CapacityExceededError,
    CorequisiteDependencyError,
    CorequisitesNotMetError,
    CourseNotInProgramError,
    EnrollmentAlreadyCancelledError,
    EnrollmentNotFoundError,
    EnrollmentPeriodInactiveError,
    GradingPeriodClosedError,
    OfferingNotAssignedError,
    PrerequisitesNotMetError,
    ScheduleConflictError,
    StudentNotEnrolledError,
)
from app.domain.exceptions.invalid_value import InvalidScheduleBlockError
from app.infrastructure.config.settings import get_settings
from app.infrastructure.logging.setup import configurar_logging
from app.interfaces.api.errors import RateLimitExceededError
from app.interfaces.api.middleware.request_logging import RequestLoggingMiddleware
from app.interfaces.api.routers import (
    admin,
    auth,
    courses,
    enrollments,
    health,
    offerings,
    periods,
    professors,
    students,
)

settings = get_settings()

# Antes de construir la aplicación: uvicorn instala sus manejadores al arrancar y hay que
# reemplazarlos, no sumarse a ellos. En la nube el formato es JSON porque quien lee estas
# líneas es Log Analytics, no una persona con la terminal abierta.
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
# sirve desde Azure Front Door y la API desde el balanceador, que son dominios distintos. Sin esta
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
# y el Application Gateway, no los clientes de la API.
app.include_router(health.router)

# Los routers de negocio sí se versionan.
app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(students.router, prefix=settings.api_v1_prefix)
app.include_router(courses.router, prefix=settings.api_v1_prefix)
app.include_router(offerings.router, prefix=settings.api_v1_prefix)
app.include_router(periods.router, prefix=settings.api_v1_prefix)
app.include_router(enrollments.router, prefix=settings.api_v1_prefix)
app.include_router(professors.router, prefix=settings.api_v1_prefix)
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
    # Fase 9: el docente pasa a ser actor. Mismos códigos y misma lógica que sus equivalentes
    # de estudiante y administrador; separarlos permite al cliente distinguir «no eres docente»
    # de «eres docente sin perfil», que se corrigen en sitios distintos.
    ProfessorRequiredError: (403, "PROFESSOR_REQUIRED"),
    ProfessorProfileNotFoundError: (404, "PROFESSOR_PROFILE_NOT_FOUND"),
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
    # Código propio y no el de arriba: las dos dicen «ya estás inscrito» y se corrigen distinto.
    # Aquella no exige hacer nada —ya está donde quería—; esta obliga a cancelar el grupo que
    # ya tiene. Compartir código dejaría a la persona sin saber cuál de las dos es la suya.
    AlreadyEnrolledInCourseError: (409, "ALREADY_ENROLLED_IN_COURSE"),
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
    # Fase 9.2. Los cuatro rechazos de calificar van separados porque se corrigen en sitios
    # distintos: revisando la URL, hablando con Registro Academico, o aceptando que las notas
    # de un semestre cerrado ya son historia.
    StudentNotEnrolledError: (404, "STUDENT_NOT_ENROLLED"),
    OfferingNotAssignedError: (403, "OFFERING_NOT_ASSIGNED"),
    GradingPeriodClosedError: (409, "GRADING_PERIOD_CLOSED"),
    CannotGradeCancelledEnrollmentError: (409, "ENROLLMENT_CANCELLED_CANNOT_GRADE"),
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
    # Fase 9.3. Los cuatro rechazos del cierre van separados porque llevan a acciones
    # distintas: no hacer nada, cerrar la ventana, perseguir notas, o revisar un choque.
    PeriodAlreadyConsolidatedError: (409, "PERIOD_ALREADY_CONSOLIDATED"),
    PeriodStillOpenError: (409, "PERIOD_STILL_OPEN"),
    PeriodHasUngradedEnrollmentsError: (409, "PERIOD_HAS_UNGRADED_ENROLLMENTS"),
    AlreadyInAcademicHistoryError: (409, "ALREADY_IN_ACADEMIC_HISTORY"),
    # 500 y no 409: no es un estado del negocio sino una incoherencia entre dos piezas. Se
    # aborta la transaccion entera porque un expediente a medias no se puede deshacer.
    InconsistentConsolidationError: (500, "INCONSISTENT_CONSOLIDATION"),
    # Los dos rechazos de la edición de requisitos (8.3 fase B). Son 409 y no 400 porque el
    # cuerpo es correcto: lo que impide aplicarlo es el ESTADO del plan —una vuelta ya
    # existente— o el de la matrícula —gente ya inscrita con la ventana cerrada—.
    ImpossibleRequirementCycleError: (409, "IMPOSSIBLE_REQUIREMENT_CYCLE"),
    RequirementWouldTrapEnrolledError: (409, "REQUIREMENT_WOULD_TRAP_ENROLLED"),
    # 409 y no 500: la escritura no se aplicó porque otra ganó la carrera, y repetir la misma
    # petición tiene todas las papeletas de funcionar. Un 500 diría que el servidor falló, que
    # es exactamente lo que no ocurrió.
    ConcurrentOfferingUpdateError: (409, "CONCURRENT_MODIFICATION"),
}


def _respuesta_error(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any],
    cabeceras_extra: dict[str, str] | None = None,
) -> JSONResponse:
    """Construye el sobre de error que `API.md` documenta como formato único.

    Recibe mensaje y detalles sueltos, y no una `DomainError`, porque no todo error con este
    formato nace en el dominio: el 429 del limitador es una protección operativa del borde y
    no una regla académica (ver `interfaces/api/errors.py`). Atarlo al tipo del dominio
    obligaría a meter en el núcleo un concepto que no le pertenece solo para reutilizar esta
    función.
    """
    # `WWW-Authenticate` acompaña a todo 401: es lo que dice el estándar HTTP y lo que permite
    # a un cliente saber CÓMO autenticarse. La ponía el guard cuando lanzaba `HTTPException`
    # directamente; al centralizar el formato de error aquí, la cabecera se centraliza con él.
    cabeceras = {"WWW-Authenticate": "Bearer"} if status_code == 401 else {}
    cabeceras.update(cabeceras_extra or {})

    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details}},
        headers=cabeceras or None,
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
            return _respuesta_error(status_code, code, exc.message, exc.details)

    return _respuesta_error(400, "DOMAIN_ERROR", exc.message, exc.details)


@app.exception_handler(RateLimitExceededError)
async def rate_limit_handler(request: Request, exc: RateLimitExceededError) -> JSONResponse:
    """Traduce el exceso de peticiones a un 429 con el mismo sobre que el resto.

    Lleva manejador propio y no entra en `_MAPEO_ERRORES` por dos razones: no es una excepción
    de dominio, y necesita una cabecera que ninguna otra respuesta usa. **`Retry-After` no es
    decorativa**: sin ella, un cliente rechazado solo puede reintentar a ciegas, y durante la
    ventana de matrícula eso significa reintentar en bucle y empeorar exactamente la situación
    que el límite existe para contener.
    """
    return _respuesta_error(
        429,
        "RATE_LIMIT_EXCEEDED",
        exc.message,
        exc.details,
        {"Retry-After": str(exc.retry_after_seconds)},
    )
