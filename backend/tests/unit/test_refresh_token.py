"""Pruebas unitarias del caso de uso de renovación de sesión."""

from __future__ import annotations

import pytest

from app.application.dtos.auth_dto import TokenType
from app.application.use_cases.auth.refresh_token import RefreshTokenUseCase
from app.domain.entities.user import User
from app.domain.exceptions.authentication import InactiveUserError, InvalidTokenError
from app.domain.value_objects.user_role import UserRole
from tests.unit.doubles import FakeAuthService, InMemoryUserRepository
from tests.unit.factories import crear_usuario


def _construir(usuario: User | None) -> tuple[RefreshTokenUseCase, FakeAuthService]:
    repositorio = InMemoryUserRepository([usuario] if usuario else [])
    servicio = FakeAuthService()
    return RefreshTokenUseCase(repositorio, servicio), servicio


@pytest.mark.unit
def test_refresh_when_token_is_valid_returns_new_access_token() -> None:
    usuario = crear_usuario()
    caso_de_uso, servicio = _construir(usuario)
    refresh = servicio.create_token(usuario.id, usuario.role, TokenType.REFRESH)

    resultado = caso_de_uso.execute(refresh_token=refresh)

    assert resultado.access_token


@pytest.mark.unit
def test_refresh_when_token_is_an_access_token_raises_invalid_token() -> None:
    # Un token de acceso no puede renovar la sesión: si pudiera, el marcado de
    # tipo no serviría de nada.
    usuario = crear_usuario()
    caso_de_uso, servicio = _construir(usuario)
    access = servicio.create_token(usuario.id, usuario.role, TokenType.ACCESS)

    with pytest.raises(InvalidTokenError):
        caso_de_uso.execute(refresh_token=access)


@pytest.mark.unit
def test_refresh_when_token_is_malformed_raises_invalid_token() -> None:
    caso_de_uso, _ = _construir(crear_usuario())

    with pytest.raises(InvalidTokenError):
        caso_de_uso.execute(refresh_token="token-basura")


@pytest.mark.unit
def test_refresh_when_account_no_longer_exists_raises_invalid_token() -> None:
    usuario = crear_usuario()
    caso_de_uso, servicio = _construir(None)
    refresh = servicio.create_token(usuario.id, usuario.role, TokenType.REFRESH)

    with pytest.raises(InvalidTokenError):
        caso_de_uso.execute(refresh_token=refresh)


@pytest.mark.unit
def test_refresh_when_account_was_deactivated_after_login_raises_inactive_user() -> None:
    # El refresh token dura 7 días: si la cuenta se desactiva en ese lapso, la
    # sesión no puede seguir renovándose.
    usuario = crear_usuario(is_active=False)
    caso_de_uso, servicio = _construir(usuario)
    refresh = servicio.create_token(usuario.id, UserRole.STUDENT, TokenType.REFRESH)

    with pytest.raises(InactiveUserError):
        caso_de_uso.execute(refresh_token=refresh)


@pytest.mark.unit
def test_refresh_when_role_changed_after_login_uses_the_current_role() -> None:
    # El rol se relee de la base de datos, no se toma del token: un token
    # emitido cuando el usuario era ADMIN no puede conservar ese permiso.
    usuario = crear_usuario(role=UserRole.STUDENT)
    caso_de_uso, servicio = _construir(usuario)
    refresh_con_rol_viejo = servicio.create_token(usuario.id, UserRole.ADMIN, TokenType.REFRESH)
    servicio.tokens_emitidos.clear()

    caso_de_uso.execute(refresh_token=refresh_con_rol_viejo)

    assert servicio.tokens_emitidos[0][1] is UserRole.STUDENT
