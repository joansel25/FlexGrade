"""Pruebas unitarias del caso de uso de inicio de sesión."""

from __future__ import annotations

import pytest

from app.application.dtos.auth_dto import TokenType
from app.application.use_cases.auth.authenticate_user import AuthenticateUserUseCase
from app.domain.exceptions.authentication import InactiveUserError, InvalidCredentialsError
from app.domain.value_objects.user_role import UserRole
from tests.unit.doubles import FakeAuthService, InMemoryUserRepository
from tests.unit.factories import PASSWORD_POR_DEFECTO, crear_usuario

CORREO = "estudiante@tdea.edu.co"


def _construir_caso_de_uso(
    *usuarios: object,
) -> tuple[AuthenticateUserUseCase, FakeAuthService]:
    repositorio = InMemoryUserRepository(list(usuarios))  # type: ignore[arg-type]
    servicio = FakeAuthService()
    return AuthenticateUserUseCase(repositorio, servicio), servicio


@pytest.mark.unit
def test_authenticate_when_credentials_are_valid_returns_access_token() -> None:
    usuario = crear_usuario(email=CORREO)
    caso_de_uso, _ = _construir_caso_de_uso(usuario)

    resultado = caso_de_uso.execute(email=CORREO, password=PASSWORD_POR_DEFECTO)

    assert resultado.tokens.access_token


@pytest.mark.unit
def test_authenticate_when_credentials_are_valid_returns_user_data() -> None:
    usuario = crear_usuario(email=CORREO)
    caso_de_uso, _ = _construir_caso_de_uso(usuario)

    resultado = caso_de_uso.execute(email=CORREO, password=PASSWORD_POR_DEFECTO)

    assert resultado.user.id == usuario.id


@pytest.mark.unit
def test_authenticate_when_credentials_are_valid_never_exposes_password_hash() -> None:
    caso_de_uso, _ = _construir_caso_de_uso(crear_usuario(email=CORREO))

    resultado = caso_de_uso.execute(email=CORREO, password=PASSWORD_POR_DEFECTO)

    assert not hasattr(resultado.user, "password_hash")


@pytest.mark.unit
def test_authenticate_when_credentials_are_valid_issues_access_and_refresh() -> None:
    caso_de_uso, servicio = _construir_caso_de_uso(crear_usuario(email=CORREO))

    caso_de_uso.execute(email=CORREO, password=PASSWORD_POR_DEFECTO)

    assert [tipo for _, _, tipo in servicio.tokens_emitidos] == [
        TokenType.ACCESS,
        TokenType.REFRESH,
    ]


@pytest.mark.unit
def test_authenticate_when_email_is_uppercase_still_finds_the_account() -> None:
    # El value object normaliza, así que el usuario puede escribir su correo
    # como quiera sin quedarse fuera del sistema.
    caso_de_uso, _ = _construir_caso_de_uso(crear_usuario(email=CORREO))

    resultado = caso_de_uso.execute(email="ESTUDIANTE@TDEA.EDU.CO", password=PASSWORD_POR_DEFECTO)

    assert resultado.user.email == CORREO


@pytest.mark.unit
def test_authenticate_when_password_is_wrong_raises_invalid_credentials() -> None:
    caso_de_uso, _ = _construir_caso_de_uso(crear_usuario(email=CORREO))

    with pytest.raises(InvalidCredentialsError):
        caso_de_uso.execute(email=CORREO, password="ClaveEquivocada")


@pytest.mark.unit
def test_authenticate_when_email_does_not_exist_raises_invalid_credentials() -> None:
    caso_de_uso, _ = _construir_caso_de_uso()

    with pytest.raises(InvalidCredentialsError):
        caso_de_uso.execute(email="nadie@tdea.edu.co", password=PASSWORD_POR_DEFECTO)


@pytest.mark.unit
def test_authenticate_when_email_is_malformed_raises_invalid_credentials_not_validation() -> None:
    # Debe responder igual que un correo inexistente: si devolviera un error de
    # validación distinto, el atacante sabría qué direcciones tienen formato
    # aceptado y podría afinar la enumeración de cuentas.
    caso_de_uso, _ = _construir_caso_de_uso()

    with pytest.raises(InvalidCredentialsError):
        caso_de_uso.execute(email="esto-no-es-un-correo", password=PASSWORD_POR_DEFECTO)


@pytest.mark.unit
def test_authenticate_when_user_is_inactive_raises_inactive_user() -> None:
    caso_de_uso, _ = _construir_caso_de_uso(crear_usuario(email=CORREO, is_active=False))

    with pytest.raises(InactiveUserError):
        caso_de_uso.execute(email=CORREO, password=PASSWORD_POR_DEFECTO)


@pytest.mark.unit
def test_authenticate_when_user_is_inactive_and_password_wrong_hides_account_state() -> None:
    # Con la contraseña equivocada NO debe revelar que la cuenta existe pero
    # está desactivada: eso confirmaría la existencia del correo.
    caso_de_uso, _ = _construir_caso_de_uso(crear_usuario(email=CORREO, is_active=False))

    with pytest.raises(InvalidCredentialsError):
        caso_de_uso.execute(email=CORREO, password="ClaveEquivocada")


@pytest.mark.unit
def test_authenticate_when_user_is_admin_token_carries_admin_role() -> None:
    caso_de_uso, servicio = _construir_caso_de_uso(crear_usuario(email=CORREO, role=UserRole.ADMIN))

    caso_de_uso.execute(email=CORREO, password=PASSWORD_POR_DEFECTO)

    assert servicio.tokens_emitidos[0][1] is UserRole.ADMIN
