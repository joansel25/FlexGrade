"""Entidad Professor: el docente que dicta un grupo."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass
class Professor:
    """Docente al que se le puede asignar un grupo, y que desde la Fase 9 puede entrar.

    Sigue siendo una entidad SEPARADA de `User`, y esa separación no es un resto histórico. Un
    docente existe como dato del catálogo antes de tener cuenta —los grupos dicen quién los
    dicta desde el día en que se abren— y sigue existiendo después de que la cuenta se borre:
    los grupos que ya dictó no pueden quedarse sin docente. `user_id` es el puente entre las dos
    cosas, y es opcional en los dos sentidos.

    Attributes:
        id: identificador único del docente.
        full_name: nombre completo.
        email: correo de contacto, si lo tiene registrado.
        user_id: cuenta con la que entra, o `None` si todavía no tiene o si se le retiró.
        created_at: instante de creación del registro.
    """

    id: UUID
    full_name: str
    email: str | None = None
    user_id: UUID | None = None
    created_at: datetime | None = field(default=None)

    def puede_entrar(self) -> bool:
        """Indica si el docente tiene cuenta con la que iniciar sesión."""
        return self.user_id is not None
