"""Adaptador de `AuthService` con JWT (PyJWT) y bcrypt."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
import jwt

from app.application.dtos.auth_dto import TokenPayload, TokenType
from app.application.ports.auth_service import AuthService
from app.domain.exceptions.authentication import InvalidTokenError
from app.domain.value_objects.user_role import UserRole
from app.infrastructure.config.settings import Settings

_ALGORITMO = "HS256"

# Coste del hashing (BEST_PRACTICES.md seccion 8). Cada incremento duplica el
# tiempo de calculo: es lo que hace inviable un ataque de fuerza bruta contra la
# base de datos si esta llegara a filtrarse.
_BCRYPT_ROUNDS = 12

# bcrypt solo considera los primeros 72 bytes de la entrada. Se rechaza por
# encima de ese limite en vez de truncar en silencio: truncar haria que dos
# contrasenas largas distintas con el mismo prefijo fueran equivalentes.
_LONGITUD_MAXIMA_BYTES = 72


class JWTAuthService(AuthService):
    """Implementación de autenticación con tokens JWT firmados con HS256.

    Recibe la configuración por constructor en vez de llamar a `get_settings()`
    internamente: así el adaptador es sustituible y comprobable con otra
    configuración sin tocar variables de entorno.
    """

    def __init__(self, settings: Settings) -> None:
        self._secret = settings.jwt_secret
        self._access_expiration = settings.jwt_expiration_seconds
        self._refresh_expiration = settings.jwt_refresh_expiration_seconds

    # ---------------------------------------------------------------- passwords

    def hash(self, plain_password: str) -> str:
        """Calcula el hash bcrypt de una contraseña.

        Raises:
            ValueError: si la contraseña supera los 72 bytes que admite bcrypt.
        """
        codificada = self._codificar(plain_password)
        return bcrypt.hashpw(codificada, bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("utf-8")

    def verify(self, plain_password: str, password_hash: str) -> bool:
        """Comprueba una contraseña contra su hash.

        `bcrypt.checkpw` compara en tiempo constante, de modo que el tiempo de
        respuesta no revela cuántos caracteres del hash coincidían.
        """
        try:
            return bcrypt.checkpw(self._codificar(plain_password), password_hash.encode("utf-8"))
        except (ValueError, TypeError):
            # Un hash almacenado con formato invalido no es una excepcion del
            # dominio: es sencillamente una verificacion fallida.
            return False

    # ------------------------------------------------------------------- tokens

    def create_token(self, user_id: UUID, role: UserRole, token_type: TokenType) -> str:
        """Emite un token firmado con la vigencia que corresponde a su tipo."""
        vigencia = (
            self._access_expiration if token_type is TokenType.ACCESS else self._refresh_expiration
        )
        emitido_en = datetime.now(timezone.utc)

        contenido = {
            "sub": str(user_id),
            "role": role.value,
            "type": token_type.value,
            "iat": emitido_en,
            "exp": emitido_en + timedelta(seconds=vigencia),
        }
        return jwt.encode(contenido, self._secret, algorithm=_ALGORITMO)

    def decode_token(self, token: str, expected_type: TokenType) -> TokenPayload:
        """Verifica firma, vigencia y tipo, y devuelve el contenido."""
        try:
            contenido = jwt.decode(
                token,
                self._secret,
                algorithms=[_ALGORITMO],
                # Se exige explicitamente `exp`: sin esta comprobacion, un token
                # emitido sin caducidad seria valido para siempre.
                options={"require": ["exp", "sub"]},
            )
        except jwt.PyJWTError as error:
            raise InvalidTokenError() from error

        tipo_recibido = contenido.get("type")
        if tipo_recibido != expected_type.value:
            # Impide usar un refresh token (7 dias) como token de acceso.
            raise InvalidTokenError(
                f"Se esperaba un token de tipo '{expected_type.value}' "
                f"y se recibió '{tipo_recibido}'"
            )

        try:
            return TokenPayload(
                user_id=UUID(str(contenido["sub"])),
                role=UserRole(contenido["role"]),
                token_type=expected_type,
            )
        except (KeyError, ValueError) as error:
            raise InvalidTokenError("El contenido del token está malformado") from error

    def access_token_expiration_seconds(self) -> int:
        """Vigencia configurada del token de acceso, en segundos."""
        return self._access_expiration

    # -------------------------------------------------------------------- utils

    @staticmethod
    def _codificar(plain_password: str) -> bytes:
        codificada = plain_password.encode("utf-8")
        if len(codificada) > _LONGITUD_MAXIMA_BYTES:
            raise ValueError(
                f"La contraseña supera los {_LONGITUD_MAXIMA_BYTES} bytes que admite bcrypt"
            )
        return codificada
