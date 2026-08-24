"""Contenedor de inyección de dependencias de FastAPI.

Es el único lugar donde las abstracciones de `application/ports/` se resuelven a
implementaciones concretas de `infrastructure/`. Los routers y los casos de uso
reciben interfaces y nunca saben qué adaptador hay detrás; cambiar PostgreSQL o
el proveedor de tokens se hace aquí, sin tocar el resto del sistema.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.application.ports.auth_service import AuthService
from app.application.ports.cache_service import CacheService
from app.application.ports.repositories.academic_history_repository import AcademicHistoryReader
from app.application.ports.repositories.course_repository import CourseRepository
from app.application.ports.repositories.enrollment_repository import EnrollmentRepository
from app.application.ports.repositories.offering_repository import OfferingRepository
from app.application.ports.repositories.period_repository import PeriodRepository
from app.application.ports.repositories.program_repository import ProgramRepository
from app.application.ports.repositories.student_repository import StudentRepository
from app.application.ports.repositories.user_repository import UserRepository
from app.application.ports.unit_of_work import UnitOfWork
from app.application.use_cases.admin.activate_enrollment_period import (
    ActivateEnrollmentPeriodUseCase,
)
from app.application.use_cases.admin.create_enrollment_period import CreateEnrollmentPeriodUseCase
from app.application.use_cases.admin.list_enrollment_periods import ListEnrollmentPeriodsUseCase
from app.application.use_cases.auth.authenticate_user import AuthenticateUserUseCase
from app.application.use_cases.auth.refresh_token import RefreshTokenUseCase
from app.application.use_cases.catalog.get_course_detail import GetCourseDetailUseCase
from app.application.use_cases.catalog.get_course_offerings import GetCourseOfferingsUseCase
from app.application.use_cases.catalog.get_current_period import GetCurrentPeriodUseCase
from app.application.use_cases.catalog.get_offering_detail import GetOfferingDetailUseCase
from app.application.use_cases.catalog.list_courses import ListCoursesUseCase
from app.application.use_cases.enrollment.cancel_enrollment import CancelEnrollmentUseCase
from app.application.use_cases.enrollment.enroll_student import EnrollStudentUseCase
from app.application.use_cases.enrollment.get_student_schedule import GetStudentScheduleUseCase
from app.infrastructure.auth.jwt_auth_service import JWTAuthService
from app.infrastructure.cache.client import get_redis_client
from app.infrastructure.cache.redis_cache_service import RedisCacheService
from app.infrastructure.config.settings import Settings, get_settings
from app.infrastructure.persistence.sqlalchemy.repositories.academic_history_repository import (
    SQLAlchemyAcademicHistoryRepository,
)
from app.infrastructure.persistence.sqlalchemy.repositories.course_repository import (
    SQLAlchemyCourseRepository,
)
from app.infrastructure.persistence.sqlalchemy.repositories.enrollment_repository import (
    SQLAlchemyEnrollmentRepository,
)
from app.infrastructure.persistence.sqlalchemy.repositories.offering_repository import (
    SQLAlchemyOfferingRepository,
)
from app.infrastructure.persistence.sqlalchemy.repositories.period_repository import (
    SQLAlchemyPeriodRepository,
)
from app.infrastructure.persistence.sqlalchemy.repositories.program_repository import (
    SQLAlchemyProgramRepository,
)
from app.infrastructure.persistence.sqlalchemy.repositories.student_repository import (
    SQLAlchemyStudentRepository,
)
from app.infrastructure.persistence.sqlalchemy.repositories.user_repository import (
    SQLAlchemyUserRepository,
)
from app.infrastructure.persistence.sqlalchemy.session import get_session
from app.infrastructure.persistence.sqlalchemy.unit_of_work import SQLAlchemyUnitOfWork

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_auth_service(settings: SettingsDep) -> AuthService:
    """Resuelve el puerto de autenticación al adaptador JWT + bcrypt."""
    return JWTAuthService(settings)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def get_user_repository(session: SessionDep) -> UserRepository:
    """Resuelve el puerto de usuarios al adaptador de SQLAlchemy."""
    return SQLAlchemyUserRepository(session)


UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]


def get_student_repository(session: SessionDep) -> StudentRepository:
    """Resuelve el puerto de estudiantes al adaptador de SQLAlchemy."""
    return SQLAlchemyStudentRepository(session)


StudentRepositoryDep = Annotated[StudentRepository, Depends(get_student_repository)]


def get_program_repository(session: SessionDep) -> ProgramRepository:
    """Resuelve el puerto de programas al adaptador de SQLAlchemy."""
    return SQLAlchemyProgramRepository(session)


ProgramRepositoryDep = Annotated[ProgramRepository, Depends(get_program_repository)]


def get_course_repository(session: SessionDep) -> CourseRepository:
    """Resuelve el puerto del catálogo de materias al adaptador de SQLAlchemy."""
    return SQLAlchemyCourseRepository(session)


CourseRepositoryDep = Annotated[CourseRepository, Depends(get_course_repository)]


def get_offering_repository(session: SessionDep) -> OfferingRepository:
    """Resuelve el puerto de grupos al adaptador de SQLAlchemy."""
    return SQLAlchemyOfferingRepository(session)


OfferingRepositoryDep = Annotated[OfferingRepository, Depends(get_offering_repository)]


def get_period_repository(session: SessionDep) -> PeriodRepository:
    """Resuelve el puerto de períodos de matrícula al adaptador de SQLAlchemy."""
    return SQLAlchemyPeriodRepository(session)


PeriodRepositoryDep = Annotated[PeriodRepository, Depends(get_period_repository)]


def get_enrollment_repository(session: SessionDep) -> EnrollmentRepository:
    """Resuelve el puerto de inscripciones al adaptador de SQLAlchemy."""
    return SQLAlchemyEnrollmentRepository(session)


EnrollmentRepositoryDep = Annotated[EnrollmentRepository, Depends(get_enrollment_repository)]


def get_academic_history_reader(session: SessionDep) -> AcademicHistoryReader:
    """Resuelve el puerto del historial académico al adaptador de SQLAlchemy."""
    return SQLAlchemyAcademicHistoryRepository(session)


AcademicHistoryReaderDep = Annotated[AcademicHistoryReader, Depends(get_academic_history_reader)]


def get_unit_of_work(session: SessionDep) -> UnitOfWork:
    """Resuelve la frontera transaccional sobre la sesión de la petición.

    Recibe la MISMA `SessionDep` que los repositorios, y de ahí depende que funcione: si
    abriera una sesión propia, sus escrituras quedarían en otra transacción y el `commit` no
    guardaría nada de lo que el caso de uso creyó escribir. FastAPI cachea el resultado de
    `get_session` dentro de una misma petición, así que la sesión es una sola.
    """
    return SQLAlchemyUnitOfWork(session)


UnitOfWorkDep = Annotated[UnitOfWork, Depends(get_unit_of_work)]


@lru_cache
@lru_cache
def get_cache_service() -> CacheService:
    """Resuelve el puerto de caché al adaptador de Redis.

    Devuelve SIEMPRE la misma instancia, y eso no es una optimización menor: el adaptador
    lleva dentro el cortacircuitos que desactiva Redis tras varios fallos seguidos. Construir
    uno nuevo en cada petición descartaría ese estado antes de que sirviera de nada, y durante
    una caída de Redis cada petición volvería a pagar el tiempo de espera completo —que es
    justo lo que el cortacircuitos existe para evitar—.

    A diferencia de los repositorios, que dependen de la sesión de la petición y por eso se
    construyen en cada una, el adaptador de caché solo depende del cliente de Redis, que ya es
    único por proceso y seguro de compartir.
    """
    return RedisCacheService(get_redis_client())


CacheServiceDep = Annotated[CacheService, Depends(get_cache_service)]


# ---------------------------------------------------------------------------
# Casos de uso del catálogo
# ---------------------------------------------------------------------------


def get_list_courses_use_case(
    course_repository: CourseRepositoryDep,
    cache: CacheServiceDep,
    settings: SettingsDep,
) -> ListCoursesUseCase:
    """Construye el caso de uso del listado del catálogo."""
    return ListCoursesUseCase(course_repository, cache, settings.catalog_cache_ttl_seconds)


def get_course_detail_use_case(
    course_repository: CourseRepositoryDep,
    cache: CacheServiceDep,
    settings: SettingsDep,
) -> GetCourseDetailUseCase:
    """Construye el caso de uso del detalle de una materia."""
    return GetCourseDetailUseCase(course_repository, cache, settings.catalog_cache_ttl_seconds)


def get_course_offerings_use_case(
    course_repository: CourseRepositoryDep,
    offering_repository: OfferingRepositoryDep,
    period_repository: PeriodRepositoryDep,
) -> GetCourseOfferingsUseCase:
    """Construye el caso de uso de los grupos de una materia.

    Sin caché: cada grupo de la respuesta lleva su `enrolled_count`, y refrescarlos todos
    costaría tanto como la consulta original. Cachear la lista entera está descartado, porque
    serviría cupos con antigüedad.
    """
    return GetCourseOfferingsUseCase(course_repository, offering_repository, period_repository)


def get_offering_detail_use_case(
    offering_repository: OfferingRepositoryDep,
    cache: CacheServiceDep,
    settings: SettingsDep,
) -> GetOfferingDetailUseCase:
    """Construye el caso de uso del detalle de un grupo."""
    return GetOfferingDetailUseCase(offering_repository, cache, settings.catalog_cache_ttl_seconds)


def get_current_period_use_case(period_repository: PeriodRepositoryDep) -> GetCurrentPeriodUseCase:
    """Construye el caso de uso del período vigente.

    Sin caché: la respuesta incluye una cuenta atrás en segundos, y servirla desde una entrada
    de hace treinta segundos mostraría un reloj que va atrasado y salta hacia atrás.
    """
    return GetCurrentPeriodUseCase(period_repository)


ListCoursesUseCaseDep = Annotated[ListCoursesUseCase, Depends(get_list_courses_use_case)]
GetCourseDetailUseCaseDep = Annotated[GetCourseDetailUseCase, Depends(get_course_detail_use_case)]
GetCourseOfferingsUseCaseDep = Annotated[
    GetCourseOfferingsUseCase, Depends(get_course_offerings_use_case)
]
GetOfferingDetailUseCaseDep = Annotated[
    GetOfferingDetailUseCase, Depends(get_offering_detail_use_case)
]
GetCurrentPeriodUseCaseDep = Annotated[
    GetCurrentPeriodUseCase, Depends(get_current_period_use_case)
]


def get_authenticate_user_use_case(
    user_repository: UserRepositoryDep,
    auth_service: AuthServiceDep,
) -> AuthenticateUserUseCase:
    """Construye el caso de uso de inicio de sesión con sus dependencias."""
    return AuthenticateUserUseCase(user_repository, auth_service)


def get_refresh_token_use_case(
    user_repository: UserRepositoryDep,
    auth_service: AuthServiceDep,
) -> RefreshTokenUseCase:
    """Construye el caso de uso de renovación de sesión."""
    return RefreshTokenUseCase(user_repository, auth_service)


AuthenticateUserUseCaseDep = Annotated[
    AuthenticateUserUseCase, Depends(get_authenticate_user_use_case)
]
RefreshTokenUseCaseDep = Annotated[RefreshTokenUseCase, Depends(get_refresh_token_use_case)]


# ---------------------------------------------------------------------------
# Casos de uso de inscripción
# ---------------------------------------------------------------------------


def get_enroll_student_use_case(
    enrollment_repository: EnrollmentRepositoryDep,
    offering_repository: OfferingRepositoryDep,
    period_repository: PeriodRepositoryDep,
    course_repository: CourseRepositoryDep,
    student_repository: StudentRepositoryDep,
    academic_history: AcademicHistoryReaderDep,
    unit_of_work: UnitOfWorkDep,
    cache: CacheServiceDep,
) -> EnrollStudentUseCase:
    """Construye el caso de uso de inscripción con sus dependencias.

    Todas son abstracciones (`ARCHITECTURE.md` sección 5, principio D): el caso de uso no sabe
    que detrás hay PostgreSQL ni Redis, y cambiar cualquiera de los dos se hace aquí.

    Los dos servicios de dominio no se inyectan: no tienen estado ni dependencias, así que el
    propio caso de uso los construye. Inyectarlos solo añadiría ruido al cableado.
    """
    return EnrollStudentUseCase(
        enrollment_repository,
        offering_repository,
        period_repository,
        course_repository,
        student_repository,
        academic_history,
        unit_of_work,
        cache,
    )


EnrollStudentUseCaseDep = Annotated[EnrollStudentUseCase, Depends(get_enroll_student_use_case)]


def get_cancel_enrollment_use_case(
    enrollment_repository: EnrollmentRepositoryDep,
    offering_repository: OfferingRepositoryDep,
    unit_of_work: UnitOfWorkDep,
    cache: CacheServiceDep,
) -> CancelEnrollmentUseCase:
    """Construye el caso de uso de cancelación."""
    return CancelEnrollmentUseCase(enrollment_repository, offering_repository, unit_of_work, cache)


def get_student_schedule_use_case(
    enrollment_repository: EnrollmentRepositoryDep,
    offering_repository: OfferingRepositoryDep,
    course_repository: CourseRepositoryDep,
    period_repository: PeriodRepositoryDep,
) -> GetStudentScheduleUseCase:
    """Construye el caso de uso del horario.

    Recibe el repositorio completo de inscripciones pero lo declara como `EnrollmentReader`:
    es de solo lectura y así queda escrito en su firma.
    """
    return GetStudentScheduleUseCase(
        enrollment_repository, offering_repository, course_repository, period_repository
    )


CancelEnrollmentUseCaseDep = Annotated[
    CancelEnrollmentUseCase, Depends(get_cancel_enrollment_use_case)
]
GetStudentScheduleUseCaseDep = Annotated[
    GetStudentScheduleUseCase, Depends(get_student_schedule_use_case)
]


# ---------------------------------------------------------------------------
# Casos de uso de administración
# ---------------------------------------------------------------------------


def get_create_enrollment_period_use_case(
    period_repository: PeriodRepositoryDep,
    unit_of_work: UnitOfWorkDep,
) -> CreateEnrollmentPeriodUseCase:
    """Construye el caso de uso de creación de ventanas de matrícula."""
    return CreateEnrollmentPeriodUseCase(period_repository, unit_of_work)


CreateEnrollmentPeriodUseCaseDep = Annotated[
    CreateEnrollmentPeriodUseCase, Depends(get_create_enrollment_period_use_case)
]


def get_activate_enrollment_period_use_case(
    period_repository: PeriodRepositoryDep,
    unit_of_work: UnitOfWorkDep,
) -> ActivateEnrollmentPeriodUseCase:
    """Construye el caso de uso de activación de ventanas."""
    return ActivateEnrollmentPeriodUseCase(period_repository, unit_of_work)


def get_list_enrollment_periods_use_case(
    period_repository: PeriodRepositoryDep,
) -> ListEnrollmentPeriodsUseCase:
    """Construye el caso de uso del listado de ventanas."""
    return ListEnrollmentPeriodsUseCase(period_repository)


ActivateEnrollmentPeriodUseCaseDep = Annotated[
    ActivateEnrollmentPeriodUseCase, Depends(get_activate_enrollment_period_use_case)
]
ListEnrollmentPeriodsUseCaseDep = Annotated[
    ListEnrollmentPeriodsUseCase, Depends(get_list_enrollment_periods_use_case)
]
