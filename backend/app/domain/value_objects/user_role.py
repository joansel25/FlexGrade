"""Rol de un usuario dentro del sistema."""

from __future__ import annotations

from enum import Enum


class UserRole(str, Enum):
    """Roles reconocidos, alineados con el CHECK de `users.role`.

    Hereda de `str` para que se serialice y compare como texto sin conversiones
    manuales en las capas externas, manteniendo a la vez el conjunto cerrado.
    """

    STUDENT = "STUDENT"
    ADMIN = "ADMIN"
    PROFESSOR = "PROFESSOR"

    def __str__(self) -> str:
        return self.value
