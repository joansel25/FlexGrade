"""Caso de uso: renovar el token de acceso con un refresh token."""

from __future__ import annotations

from app.application.dtos.auth_dto import AuthenticatedUserDTO, TokenPairDTO, TokenType
from app.application.ports.auth_service import AuthService
from app.application.ports.repositories.user_repository import UserRepository
from app.domain.exceptions.authentication import InvalidTokenError


class RefreshTokenUseCase:
    """Emite un par de tokens nuevo a partir de un refresh token válido."""

    def __init__(self, user_repository: UserRepository, auth_service: AuthService) -> None:
        self._user_repository = user_repository
        self._auth_service = auth_service

    def execute(self, refresh_token: str) -> TokenPairDTO:
        """Renueva la sesión.

        Args:
            refresh_token: el token de refresco entregado en el login.

        Returns:
            Un par de tokens nuevo.

        Raises:
            InvalidTokenError: si el token no es válido, ha expirado, no es de
                tipo refresh, o la cuenta ya no existe.
            InactiveUserError: si la cuenta fue desactivada tras el login.
        """
        contenido = self._auth_service.decode_token(refresh_token, TokenType.REFRESH)

        # Se relee la cuenta en vez de confiar en el rol que viaja en el token:
        # entre el login y el refresco el usuario pudo ser desactivado o haber
        # cambiado de rol, y un token de 7 dias no puede perpetuar permisos
        # que ya se revocaron.
        usuario = self._user_repository.find_by_id(contenido.user_id)

        if usuario is None:
            raise InvalidTokenError("La cuenta asociada al token ya no existe")

        usuario.ensure_can_authenticate()

        return TokenPairDTO(
            access_token=self._auth_service.create_token(
                usuario.id, usuario.role, TokenType.ACCESS
            ),
            refresh_token=self._auth_service.create_token(
                usuario.id, usuario.role, TokenType.REFRESH
            ),
            expires_in=self._auth_service.access_token_expiration_seconds(),
            # La cuenta viaja de vuelta porque el refresco es lo que restaura la sesión al
            # recargar la página, y sin ella el frontend no sabría con qué rol entró. El usuario
            # ya está cargado aquí arriba para comprobar que sigue activo: no cuesta una
            # consulta más.
            user=AuthenticatedUserDTO(id=usuario.id, email=usuario.email.value, role=usuario.role),
        )
