"""Entidad User: la cuenta con la que alguien accede al sistema."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.domain.exceptions.authentication import InactiveUserError
from app.domain.value_objects.email import Email
from app.domain.value_objects.user_role import UserRole


@dataclass
class User:
    """Cuenta de autenticación, común a estudiantes y administradores.

    La entidad decide si una cuenta puede autenticarse y qué puede hacer según su
    rol. No sabe cómo se verifican las contraseñas: `password_hash` es un dato
    opaco que produce y comprueba el adaptador de autenticación.

    Attributes:
        id: identificador único de la cuenta.
        email: correo institucional, validado como value object.
        password_hash: hash de la contraseña. La entidad nunca lo interpreta.
        role: rol que determina los permisos.
        is_active: si la cuenta está habilitada para entrar.
        created_at: instante de creación.
        updated_at: instante de la última modificación.
    """

    id: UUID
    email: Email
    password_hash: str
    role: UserRole
    is_active: bool = True
    created_at: datetime | None = field(default=None)
    updated_at: datetime | None = field(default=None)

    def is_admin(self) -> bool:
        """Indica si la cuenta tiene rol administrativo."""
        return self.role is UserRole.ADMIN

    def is_student(self) -> bool:
        """Indica si la cuenta tiene rol de estudiante."""
        return self.role is UserRole.STUDENT

    def ensure_can_authenticate(self) -> None:
        """Verifica que la cuenta esté habilitada para iniciar sesión.

        Se comprueba DESPUÉS de validar la contraseña: informar de que una cuenta
        está desactivada antes de verificar credenciales revelaría que ese correo
        existe en el sistema.

        Raises:
            InactiveUserError: si la cuenta está desactivada.
        """
        if not self.is_active:
            raise InactiveUserError()

    def deactivate(self) -> None:
        """Deshabilita la cuenta sin borrarla, preservando su historial."""
        self.is_active = False

    def activate(self) -> None:
        """Vuelve a habilitar una cuenta previamente desactivada."""
        self.is_active = True
