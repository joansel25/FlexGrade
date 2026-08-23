"""Caso de uso: iniciar sesión con correo y contraseña."""

from __future__ import annotations

from app.application.dtos.auth_dto import (
    AuthenticatedUserDTO,
    LoginResultDTO,
    TokenPairDTO,
    TokenType,
)
from app.application.ports.auth_service import AuthService
from app.application.ports.repositories.user_repository import UserRepository
from app.domain.exceptions.authentication import InvalidCredentialsError
from app.domain.exceptions.invalid_value import InvalidEmailError
from app.domain.value_objects.email import Email


class AuthenticateUserUseCase:
    """Valida credenciales y emite el par de tokens de la sesión.

    Orquesta, no decide: la validez de la cuenta la determina la entidad `User`
    y la verificación criptográfica la hace el adaptador de autenticación.
    """

    def __init__(self, user_repository: UserRepository, auth_service: AuthService) -> None:
        self._user_repository = user_repository
        self._auth_service = auth_service

    def execute(self, email: str, password: str) -> LoginResultDTO:
        """Autentica a un usuario y devuelve sus tokens.

        Args:
            email: correo tal como lo escribió el usuario.
            password: contraseña en claro.

        Returns:
            Los tokens emitidos y los datos públicos de la cuenta.

        Raises:
            InvalidCredentialsError: si el correo no existe o la contraseña no
                coincide.
            InactiveUserError: si las credenciales son correctas pero la cuenta
                está desactivada.
        """
        try:
            correo = Email(email)
        except InvalidEmailError as error:
            # Un correo mal formado no puede existir en la base de datos. Se
            # responde igual que si no existiera, para no revelar por el tipo de
            # error qué direcciones estan registradas.
            raise InvalidCredentialsError() from error

        usuario = self._user_repository.find_by_email(correo)

        if usuario is None or not self._auth_service.verify(password, usuario.password_hash):
            raise InvalidCredentialsError()

        # Se comprueba DESPUES de validar la contrasena: hacerlo antes revelaria
        # que ese correo existe en el sistema a quien no conoce la clave.
        usuario.ensure_can_authenticate()

        return LoginResultDTO(
            tokens=TokenPairDTO(
                access_token=self._auth_service.create_token(
                    usuario.id, usuario.role, TokenType.ACCESS
                ),
                refresh_token=self._auth_service.create_token(
                    usuario.id, usuario.role, TokenType.REFRESH
                ),
                expires_in=self._auth_service.access_token_expiration_seconds(),
            ),
            user=AuthenticatedUserDTO(
                id=usuario.id,
                email=usuario.email.value,
                role=usuario.role,
            ),
        )
