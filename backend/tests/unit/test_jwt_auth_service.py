"""Pruebas del adaptador real de autenticación (PyJWT + bcrypt).

Los casos de uso se prueban con un doble determinista; aquí se verifica la
criptografía de verdad, que es lo que ese doble no puede cubrir.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.application.dtos.auth_dto import TokenType
from app.domain.exceptions.authentication import InvalidTokenError
from app.domain.value_objects.user_role import UserRole
from app.infrastructure.auth.jwt_auth_service import JWTAuthService
from app.infrastructure.config.settings import Settings


def _servicio(secret: str = "secreto-de-pruebas-suficientemente-largo") -> JWTAuthService:
    return JWTAuthService(
        Settings(
            database_url="postgresql+psycopg://x:x@localhost:5432/x",
            redis_url="redis://localhost:6379/0",
            jwt_secret=secret,
        )
    )


@pytest.mark.unit
def test_hash_when_called_twice_produces_different_hashes() -> None:
    # bcrypt genera una sal distinta cada vez: dos usuarios con la misma
    # contraseña no comparten hash, lo que impide identificarlos por comparación.
    servicio = _servicio()

    assert servicio.hash("SecurePass123") != servicio.hash("SecurePass123")


@pytest.mark.unit
def test_verify_when_password_is_correct_returns_true() -> None:
    servicio = _servicio()

    assert servicio.verify("SecurePass123", servicio.hash("SecurePass123")) is True


@pytest.mark.unit
def test_verify_when_password_is_wrong_returns_false() -> None:
    servicio = _servicio()

    assert servicio.verify("ClaveEquivocada", servicio.hash("SecurePass123")) is False


@pytest.mark.unit
def test_verify_when_stored_hash_is_corrupt_returns_false_instead_of_raising() -> None:
    assert _servicio().verify("SecurePass123", "esto-no-es-un-hash-bcrypt") is False


@pytest.mark.unit
def test_hash_when_password_exceeds_bcrypt_limit_raises_value_error() -> None:
    # Se rechaza en vez de truncar: bcrypt ignora lo que pase de 72 bytes, así
    # que truncar haría equivalentes dos contraseñas largas con igual prefijo.
    with pytest.raises(ValueError):
        _servicio().hash("a" * 73)


@pytest.mark.unit
def test_decode_token_when_token_is_valid_returns_the_user_id() -> None:
    servicio = _servicio()
    user_id = uuid4()
    token = servicio.create_token(user_id, UserRole.STUDENT, TokenType.ACCESS)

    assert servicio.decode_token(token, TokenType.ACCESS).user_id == user_id


@pytest.mark.unit
def test_decode_token_when_token_is_valid_returns_the_role() -> None:
    servicio = _servicio()
    token = servicio.create_token(uuid4(), UserRole.ADMIN, TokenType.ACCESS)

    assert servicio.decode_token(token, TokenType.ACCESS).role is UserRole.ADMIN


@pytest.mark.unit
def test_decode_token_when_refresh_token_used_as_access_raises_invalid_token() -> None:
    # Es la defensa que impide que un token de 7 días sirva para llamar a la API.
    servicio = _servicio()
    refresh = servicio.create_token(uuid4(), UserRole.STUDENT, TokenType.REFRESH)

    with pytest.raises(InvalidTokenError):
        servicio.decode_token(refresh, TokenType.ACCESS)


@pytest.mark.unit
def test_decode_token_when_signed_with_another_secret_raises_invalid_token() -> None:
    # Sin esta comprobación, cualquiera podría fabricar tokens con el rol ADMIN.
    token_ajeno = _servicio("otro-secreto-completamente-distinto").create_token(
        uuid4(), UserRole.ADMIN, TokenType.ACCESS
    )

    with pytest.raises(InvalidTokenError):
        _servicio().decode_token(token_ajeno, TokenType.ACCESS)


@pytest.mark.unit
def test_decode_token_when_token_is_garbage_raises_invalid_token() -> None:
    with pytest.raises(InvalidTokenError):
        _servicio().decode_token("no.es.un.jwt", TokenType.ACCESS)
