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
from app.application.ports.repositories.course_repository import CourseRepository
from app.application.ports.repositories.offering_repository import OfferingRepository
from app.application.ports.repositories.period_repository import PeriodRepository
from app.application.ports.repositories.program_repository import ProgramRepository
from app.application.ports.repositories.student_repository import StudentRepository
from app.application.ports.repositories.user_repository import UserRepository
from app.application.use_cases.auth.authenticate_user import AuthenticateUserUseCase
from app.application.use_cases.auth.refresh_token import RefreshTokenUseCase
from app.application.use_cases.catalog.get_course_detail import GetCourseDetailUseCase
from app.application.use_cases.catalog.get_course_offerings import GetCourseOfferingsUseCase
from app.application.use_cases.catalog.get_current_period import GetCurrentPeriodUseCase
from app.application.use_cases.catalog.get_offering_detail import GetOfferingDetailUseCase
from app.application.use_cases.catalog.list_courses import ListCoursesUseCase
from app.infrastructure.auth.jwt_auth_service import JWTAuthService
from app.infrastructure.cache.client import get_redis_client
from app.infrastructure.cache.redis_cache_service import RedisCacheService
from app.infrastructure.config.settings import Settings, get_settings
from app.infrastructure.persistence.sqlalchemy.repositories.course_repository import (
    SQLAlchemyCourseRepository,
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
