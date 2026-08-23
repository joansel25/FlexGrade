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
from app.application.ports.repositories.student_repository import StudentRepository
from app.application.ports.repositories.user_repository import UserRepository
from app.application.use_cases.auth.authenticate_user import AuthenticateUserUseCase
from app.application.use_cases.auth.refresh_token import RefreshTokenUseCase
from app.infrastructure.auth.jwt_auth_service import JWTAuthService
from app.infrastructure.config.settings import Settings, get_settings
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
