"""DTOs del flujo de autenticación.

Son estructuras planas de transporte entre capas. No llevan comportamiento de
negocio (eso vive en las entidades) ni validación de esquema HTTP (eso vive en
los schemas Pydantic de `interfaces/api/`).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from app.domain.value_objects.user_role import UserRole


class TokenType(str, Enum):
    """Tipo de token emitido.

    Se incluye dentro del propio token para que un refresh token no pueda usarse
    como token de acceso: sin esta marca, el token de 7 días serviría para
    llamar a la API, anulando la ventaja de que el de acceso dure solo 1 hora.
    """

    ACCESS = "access"
    REFRESH = "refresh"


@dataclass(frozen=True)
class TokenPayload:
    """Contenido verificado de un token ya decodificado.

    Attributes:
        user_id: cuenta a la que pertenece el token.
        role: rol de esa cuenta en el momento de la emisión.
        token_type: si es un token de acceso o de refresco.
    """

    user_id: UUID
    role: UserRole
    token_type: TokenType


@dataclass(frozen=True)
class AuthenticatedUserDTO:
    """Datos públicos de la cuenta autenticada.

    Nunca incluye el `password_hash`: es un dato que no sale de la capa de
    persistencia.

    Attributes:
        id: identificador de la cuenta.
        email: correo institucional.
        role: rol de la cuenta.
    """

    id: UUID
    email: str
    role: UserRole


@dataclass(frozen=True)
class TokenPairDTO:
    """Par de tokens entregado tras un inicio de sesión o un refresco.

    Attributes:
        access_token: token de vida corta para llamar a la API.
        refresh_token: token de vida larga que permite obtener uno nuevo.
        expires_in: segundos de vigencia del token de acceso.
        user: la cuenta a la que pertenecen. Va también en el refresco, y no solo en el login,
            porque al recargar la página el frontend restaura la sesión con el refresh token y
            hasta ahora se quedaba sin saber QUIÉN había entrado. Con el rol perdido, unas rutas
            protegidas por rol —las de administración de la Fase 8— expulsarían a un
            administrador legítimo en cuanto recargara. El caso de uso ya carga el usuario para
            comprobar que sigue activo, así que devolverlo no cuesta ninguna consulta más.
    """

    access_token: str
    refresh_token: str
    expires_in: int
    user: AuthenticatedUserDTO | None = None


@dataclass(frozen=True)
class LoginResultDTO:
    """Resultado completo de `POST /auth/login`.

    Attributes:
        tokens: el par de tokens emitido.
        user: los datos públicos de la cuenta.
    """

    tokens: TokenPairDTO
    user: AuthenticatedUserDTO
