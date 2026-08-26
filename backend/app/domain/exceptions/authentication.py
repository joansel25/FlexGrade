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


class ProfessorProfileNotFoundError(DomainError):
    """La cuenta está autenticada y tiene rol de docente, pero no hay perfil que le corresponda.

    Es 404 y no 403, igual que su equivalente de estudiante: la cuenta es válida y el permiso
    está, lo que no existe es el perfil. Ocurre cuando se le da el rol a una cuenta sin
    enlazarla a una fila de `professors`, que es un error de alta, no de permisos, y responder
    403 mandaría a corregirlo donde no está.
    """

    def __init__(self, message: str = "El usuario no tiene un perfil de docente") -> None:
        super().__init__(message)


class ProfessorRequiredError(DomainError):
    """La cuenta está autenticada pero no tiene rol de docente.

    Es 403 por lo mismo que `AdminRequiredError`: la identidad quedó probada y lo que falta es
    el permiso. Un 401 haría que el cliente intentara volver a autenticarse, lo que no arregla
    nada.
    """

    def __init__(self, message: str = "Se requiere rol de docente") -> None:
        super().__init__(message)


class MissingTokenError(DomainError):
    """La petición no trae la cabecera `Authorization`.

    Se distingue de `InvalidTokenError` a propósito: para el cliente son situaciones distintas
    —una se resuelve iniciando sesión, la otra renovando el token— y sin códigos separados
    tendría que decidirlo interpretando el mensaje en español.
    """

    def __init__(self, message: str = "Falta la cabecera Authorization") -> None:
        super().__init__(message)


class AdminRequiredError(DomainError):
    """La cuenta está autenticada pero no tiene rol de administrador.

    Es 403 y no 401 porque el problema no es la identidad, que quedó probada, sino el permiso.
    Devolver 401 haría que el cliente intentara volver a autenticarse, lo que no arreglaría
    nada.
    """

    def __init__(self, message: str = "Se requiere rol de administrador") -> None:
        super().__init__(message)
