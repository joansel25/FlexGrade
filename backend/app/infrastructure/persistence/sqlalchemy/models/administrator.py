"""Modelo ORM de la tabla `administrators`: el perfil del personal de gestión académica.

Corresponde al DDL de `docs/DATA_MODEL.md` sección 2. Igual que `students`, es el complemento de
perfil de una cuenta de `users`, en este caso con rol `ADMIN`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.sqlalchemy.models.base import Base


class AdministratorModel(Base):
    """Perfil administrativo asociado a una cuenta de usuario con rol `ADMIN`.

    Attributes:
        id: identificador único, generado por PostgreSQL con `gen_random_uuid()`.
        user_id: cuenta de autenticación asociada. `ON DELETE CASCADE`, misma razón que en
            `students`: el perfil no sobrevive a la cuenta.
        full_name: nombre completo del administrador.
        department: dependencia a la que pertenece. Opcional: no toda institución la registra.
        created_at: instante de creación del registro.
    """

    __tablename__ = "administrators"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
