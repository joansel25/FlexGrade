"""Dependencias de autenticación y autorización de la API.

Aquí vive el guard que protege los endpoints. La identidad del usuario sale
SIEMPRE del token, nunca del cuerpo ni de la query de la petición: aceptar un
`user_id` enviado por el cliente permitiría a cualquiera actuar en nombre de
otro (IDOR).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.dtos.auth_dto import TokenPayload, TokenType
from app.domain.exceptions.authentication import InvalidTokenError
from app.domain.value_objects.user_role import UserRole
from app.interfaces.api.dependencies.di import AuthServiceDep

# `auto_error=False` para construir nosotros la respuesta 401: el 403 que
# devuelve HTTPBearer por defecto ante un header ausente no distingue "no te has
# autenticado" de "no tienes permiso", que son cosas distintas para el cliente.
_esquema_bearer = HTTPBearer(auto_error=False, description="Token JWT de acceso")


def get_current_user(
    auth_service: AuthServiceDep,
    credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(_esquema_bearer)] = None,
) -> TokenPayload:
    """Valida el token de acceso y devuelve la identidad del solicitante.

    Args:
        auth_service: servicio que verifica la firma y la vigencia del token.
        credenciales: cabecera `Authorization: Bearer <token>`, si viene.

    Returns:
        El contenido verificado del token.

    Raises:
        HTTPException: 401 si no hay token o si no es válido.
    """
    if credenciales is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta la cabecera Authorization",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return auth_service.decode_token(credenciales.credentials, TokenType.ACCESS)
    except InvalidTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error.message,
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


CurrentUserDep = Annotated[TokenPayload, Depends(get_current_user)]


def require_admin(current_user: CurrentUserDep) -> TokenPayload:
    """Exige que el solicitante tenga rol de administrador.

    Se aplica a todos los endpoints bajo `/admin`. La comprobación se hace en el
    backend aunque el frontend ya oculte la opción: nunca se confía en el cliente.

    Args:
        current_user: identidad ya validada por `get_current_user`.

    Returns:
        La misma identidad, si tiene permiso.

    Raises:
        HTTPException: 403 si el rol no es ADMIN. Es 403 y no 401 porque el
            usuario sí está autenticado; lo que falta es autorización.
    """
    if current_user.role is not UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol de administrador",
        )
    return current_user


AdminUserDep = Annotated[TokenPayload, Depends(require_admin)]
