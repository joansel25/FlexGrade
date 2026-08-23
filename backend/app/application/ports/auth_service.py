"""Puertos del servicio de autenticación.

El contrato se declara segregado en dos responsabilidades con razones distintas
para cambiar (`BEST_PRACTICES.md`, principio de segregación de interfaces):

- `PasswordHasher` cambia si cambia el algoritmo de hashing o su coste.
- `TokenService` cambia si cambia el formato o el algoritmo de firma del token.

`AuthService` los compone para el caso habitual, en el que un único adaptador
cubre ambos. Un caso de uso que solo verifique tokens (como el guard de las
dependencias de FastAPI) depende únicamente de `TokenService`, no del contrato
completo.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.application.dtos.auth_dto import TokenPayload, TokenType
from app.domain.value_objects.user_role import UserRole


class PasswordHasher(ABC):
    """Contrato de hashing y verificación de contraseñas."""

    @abstractmethod
    def hash(self, plain_password: str) -> str:
        """Calcula el hash de una contraseña en claro.

        Args:
            plain_password: la contraseña tal como la escribió el usuario.

        Returns:
            El hash listo para persistirse.
        """

    @abstractmethod
    def verify(self, plain_password: str, password_hash: str) -> bool:
        """Comprueba si una contraseña corresponde a un hash.

        La implementación debe usar una comparación en tiempo constante para no
        filtrar información por el tiempo de respuesta.

        Args:
            plain_password: la contraseña a comprobar.
            password_hash: el hash almacenado.

        Returns:
            `True` si coinciden.
        """


class TokenService(ABC):
    """Contrato de emisión y verificación de tokens."""

    @abstractmethod
    def create_token(self, user_id: UUID, role: UserRole, token_type: TokenType) -> str:
        """Emite un token firmado para una cuenta.

        Args:
            user_id: cuenta a la que pertenece el token.
            role: rol de la cuenta.
            token_type: si es de acceso o de refresco; determina la vigencia.

        Returns:
            El token codificado.
        """

    @abstractmethod
    def decode_token(self, token: str, expected_type: TokenType) -> TokenPayload:
        """Verifica un token y devuelve su contenido.

        Args:
            token: el token recibido del cliente.
            expected_type: tipo que debe tener; si no coincide, se rechaza.

        Returns:
            El contenido verificado del token.

        Raises:
            InvalidTokenError: si la firma no es válida, el token ha expirado,
                está malformado o su tipo no es el esperado.
        """

    @abstractmethod
    def access_token_expiration_seconds(self) -> int:
        """Vigencia configurada del token de acceso, en segundos."""


class AuthService(PasswordHasher, TokenService, ABC):
    """Contrato completo de autenticación: contraseñas y tokens."""
