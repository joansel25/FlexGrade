"""Adaptador de `UserRepository` sobre SQLAlchemy."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.ports.repositories.user_repository import UserRepository
from app.domain.entities.user import User
from app.domain.value_objects.email import Email
from app.domain.value_objects.user_role import UserRole
from app.infrastructure.persistence.sqlalchemy.models.user import UserModel


class SQLAlchemyUserRepository(UserRepository):
    """Implementación del puerto de usuarios contra PostgreSQL.

    Traduce en ambos sentidos entre `UserModel` (persistencia) y `User`
    (dominio). Ese mapeo explícito es el precio de que el dominio no conozca el
    ORM, y es lo que permite probar las reglas de negocio sin base de datos.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_id(self, user_id: UUID) -> User | None:
        modelo = self._session.get(UserModel, user_id)
        return self._a_entidad(modelo) if modelo is not None else None

    def find_by_email(self, email: Email) -> User | None:
        # Se compara contra el valor normalizado del value object: `Email` ya
        # pasó la dirección a minúsculas, así que la búsqueda es determinista.
        sentencia = select(UserModel).where(UserModel.email == email.value)
        modelo = self._session.execute(sentencia).scalar_one_or_none()
        return self._a_entidad(modelo) if modelo is not None else None

    def save(self, user: User) -> None:
        modelo = self._session.get(UserModel, user.id)

        if modelo is None:
            self._session.add(self._a_modelo(user))
            return

        modelo.email = user.email.value
        modelo.password_hash = user.password_hash
        modelo.role = user.role.value
        modelo.is_active = user.is_active

    @staticmethod
    def _a_entidad(modelo: UserModel) -> User:
        """Convierte el modelo ORM en la entidad del dominio."""
        return User(
            id=modelo.id,
            email=Email(modelo.email),
            password_hash=modelo.password_hash,
            role=UserRole(modelo.role),
            is_active=modelo.is_active,
            created_at=modelo.created_at,
            updated_at=modelo.updated_at,
        )

    @staticmethod
    def _a_modelo(user: User) -> UserModel:
        """Convierte la entidad del dominio en el modelo ORM.

        `created_at` y `updated_at` no se asignan: los gestiona la base de datos
        con su `DEFAULT NOW()` y el trigger `trg_users_updated_at`.
        """
        return UserModel(
            id=user.id,
            email=user.email.value,
            password_hash=user.password_hash,
            role=user.role.value,
            is_active=user.is_active,
        )
