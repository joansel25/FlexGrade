"""Puerto de persistencia del agregado User."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.user import User
from app.domain.value_objects.email import Email


class UserRepository(ABC):
    """Contrato de acceso a las cuentas de autenticación.

    Los métodos hablan el lenguaje del dominio (`find_by_email`), no el de la
    base de datos (`select_where`). No existe un repositorio genérico
    `IRepository[T]`: escondería ese lenguaje y obligaría a filtrar en memoria.
    """

    @abstractmethod
    def find_by_id(self, user_id: UUID) -> User | None:
        """Recupera una cuenta por su identificador.

        Args:
            user_id: identificador de la cuenta.

        Returns:
            La cuenta, o `None` si no existe.
        """

    @abstractmethod
    def find_by_email(self, email: Email) -> User | None:
        """Recupera una cuenta por su correo electrónico.

        Es la consulta que sostiene el inicio de sesión.

        Args:
            email: correo institucional a buscar.

        Returns:
            La cuenta, o `None` si ningún usuario tiene ese correo.
        """

    @abstractmethod
    def save(self, user: User) -> None:
        """Persiste una cuenta nueva o los cambios de una existente.

        Args:
            user: la entidad a persistir.
        """
