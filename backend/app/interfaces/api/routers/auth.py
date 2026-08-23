"""Router de autenticación.

Los handlers son deliberadamente delgados: reciben el request ya validado por
Pydantic, invocan el caso de uso y traducen el resultado al schema de respuesta.
Las excepciones de dominio las traduce a HTTP el manejador centralizado de
`main.py`, no un `try/except` repetido en cada endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.interfaces.api.dependencies.auth import CurrentUserDep
from app.interfaces.api.dependencies.di import AuthenticateUserUseCaseDep, RefreshTokenUseCaseDep
from app.interfaces.api.schemas.auth_schemas import (
    AuthenticatedUserSchema,
    LoginRequestSchema,
    LoginResponseSchema,
    RefreshRequestSchema,
    TokenPairSchema,
)
from app.interfaces.api.schemas.error_schemas import ErrorResponseSchema

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=LoginResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Iniciar sesión",
    responses={401: {"model": ErrorResponseSchema, "description": "Credenciales inválidas"}},
)
def login(
    payload: LoginRequestSchema,
    use_case: AuthenticateUserUseCaseDep,
) -> LoginResponseSchema:
    """Autentica al usuario y devuelve el par de tokens de la sesión."""
    resultado = use_case.execute(email=payload.email, password=payload.password)

    return LoginResponseSchema(
        access_token=resultado.tokens.access_token,
        refresh_token=resultado.tokens.refresh_token,
        expires_in=resultado.tokens.expires_in,
        user=AuthenticatedUserSchema(
            id=resultado.user.id,
            email=resultado.user.email,
            role=resultado.user.role.value,
        ),
    )


@router.post(
    "/refresh",
    response_model=TokenPairSchema,
    status_code=status.HTTP_200_OK,
    summary="Renovar el token de acceso",
    responses={401: {"model": ErrorResponseSchema, "description": "Refresh token inválido"}},
)
def refresh(
    payload: RefreshRequestSchema,
    use_case: RefreshTokenUseCaseDep,
) -> TokenPairSchema:
    """Emite un par de tokens nuevo a partir de un refresh token válido."""
    tokens = use_case.execute(refresh_token=payload.refresh_token)

    return TokenPairSchema(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cerrar sesión",
    responses={401: {"model": ErrorResponseSchema, "description": "Token ausente o inválido"}},
)
def logout(current_user: CurrentUserDep) -> Response:
    """Cierra la sesión del usuario autenticado.

    LIMITACIÓN CONOCIDA: los JWT son autocontenidos y sin estado, así que el
    servidor no puede invalidar un token ya emitido sin llevar un registro de
    revocados. Hoy este endpoint solo verifica que el token sea válido y
    responde 204; la invalidación real es que el cliente descarte los tokens.

    Como el access token dura una hora, la ventana de exposición es acotada. La
    revocación efectiva (lista de denegación del `jti` en Redis, consultada por
    `get_current_user`) se implementará junto con el adaptador de Redis en la
    Fase 2. Está anotado así en `API.md`.
    """
    return Response(status_code=status.HTTP_204_NO_CONTENT)
