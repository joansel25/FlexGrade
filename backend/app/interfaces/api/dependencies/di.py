"""Contenedor de inyección de dependencias de FastAPI.

Es el único lugar donde las abstracciones de `application/ports/` se resuelven a
implementaciones concretas de `infrastructure/`. Los routers y los casos de uso
reciben interfaces y nunca saben qué adaptador hay detrás; cambiar PostgreSQL o
el proveedor de tokens se hace aquí, sin tocar el resto del sistema.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.application.ports.auth_service import AuthService
from app.application.ports.repositories.course_repository import CourseRepository
from app.application.ports.repositories.offering_repository import OfferingRepository
from app.application.ports.repositories.period_repository import PeriodRepository
from app.application.ports.repositories.program_repository import ProgramRepository
from app.application.ports.repositories.student_repository import StudentRepository
from app.application.ports.repositories.user_repository import UserRepository
from app.application.use_cases.auth.authenticate_user import AuthenticateUserUseCase
from app.application.use_cases.auth.refresh_token import RefreshTokenUseCase
from app.infrastructure.auth.jwt_auth_service import JWTAuthService
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
