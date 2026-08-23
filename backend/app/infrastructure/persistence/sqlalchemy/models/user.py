"""Modelo ORM de la tabla `users`: la cuenta de autenticación.

Corresponde al DDL de `docs/DATA_MODEL.md` sección 2. `users` es la base común de estudiantes y
administradores: guarda credenciales y rol, mientras que los datos de perfil viven en `students`
y `administrators`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, String, func, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.sqlalchemy.models.base import Base


class UserModel(Base):
    """Cuenta de autenticación de una persona del sistema.

    Attributes:
        id: identificador único, generado por PostgreSQL con `gen_random_uuid()`.
        email: correo institucional; identificador natural con el que se inicia sesión.
        password_hash: hash de la contraseña. Nunca la contraseña en claro.
        role: `STUDENT` o `ADMIN`. Restringido por un `CHECK` en la base de datos para que
            ningún camino de escritura pueda introducir un rol desconocido.
        is_active: permite deshabilitar una cuenta sin borrarla ni perder su historial.
        created_at: instante de creación de la cuenta.
        updated_at: instante de la última modificación.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        # Nombre corto a propósito: la `naming_convention` de `Base` lo expande a `ck_users_role`.
        CheckConstraint("role IN ('STUDENT', 'ADMIN')", name="role"),
        # `email` no lleva indice propio: la restriccion UNIQUE ya crea su indice B-tree
        # (BEST_PRACTICES.md, "Convenciones de base de datos").
    )
