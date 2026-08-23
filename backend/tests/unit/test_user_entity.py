"""Pruebas unitarias de la entidad User."""

from __future__ import annotations

import pytest

from app.domain.exceptions.authentication import InactiveUserError
from app.domain.value_objects.user_role import UserRole
from tests.unit.factories import crear_usuario


@pytest.mark.unit
def test_is_admin_when_role_is_admin_returns_true() -> None:
    assert crear_usuario(role=UserRole.ADMIN).is_admin() is True


@pytest.mark.unit
def test_is_admin_when_role_is_student_returns_false() -> None:
    assert crear_usuario(role=UserRole.STUDENT).is_admin() is False


@pytest.mark.unit
def test_ensure_can_authenticate_when_user_is_active_does_not_raise() -> None:
    crear_usuario(is_active=True).ensure_can_authenticate()


@pytest.mark.unit
def test_ensure_can_authenticate_when_user_is_inactive_raises_inactive_user() -> None:
    with pytest.raises(InactiveUserError):
        crear_usuario(is_active=False).ensure_can_authenticate()


@pytest.mark.unit
def test_deactivate_when_called_marks_user_as_inactive() -> None:
    usuario = crear_usuario(is_active=True)

    usuario.deactivate()

    assert usuario.is_active is False
