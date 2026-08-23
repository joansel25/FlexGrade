"""Entidad Professor: el docente que dicta un grupo."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass
class Professor:
    """Docente al que se le puede asignar un grupo.

    No es un usuario del sistema: no inicia sesión ni tiene rol. Para el catálogo es el dato
    que responde "quién dicta este grupo", y por eso vive fuera de `User`.

    Attributes:
        id: identificador único del docente.
        full_name: nombre completo.
        email: correo de contacto, si lo tiene registrado.
        created_at: instante de creación del registro.
    """

    id: UUID
    full_name: str
    email: str | None = None
    created_at: datetime | None = field(default=None)
