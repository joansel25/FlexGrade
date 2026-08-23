"""Errores del dominio de autenticación."""

from __future__ import annotations

from app.domain.exceptions.base import DomainError


class InvalidCredentialsError(DomainError):
    """El correo no existe o la contraseña no coincide.

    Deliberadamente NO distingue entre ambos casos: revelar cuál de los dos
    falló permite enumerar qué correos están registrados en el sistema.
    """

    def __init__(self, message: str = "Correo o contraseña incorrectos") -> None:
        super().__init__(message)


class InactiveUserError(DomainError):
    """Las credenciales son correctas pero la cuenta está desactivada."""

    def __init__(self, message: str = "La cuenta está desactivada") -> None:
        super().__init__(message)


class InvalidTokenError(DomainError):
    """El token es ilegible, tiene una firma inválida o ha expirado."""

    def __init__(self, message: str = "El token no es válido o ha expirado") -> None:
        super().__init__(message)


class StudentProfileNotFoundError(DomainError):
    """El usuario está autenticado pero no tiene perfil de estudiante asociado."""

    def __init__(self, message: str = "El usuario no tiene un perfil de estudiante") -> None:
        super().__init__(message)
