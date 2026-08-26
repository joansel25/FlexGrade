"""Modelo ORM de la tabla `professors`: el docente que dicta un grupo.

Corresponde al DDL de `docs/DATA_MODEL.md` sección 2. El profesor no es un usuario del sistema:
no inicia sesión ni tiene rol en `users`. Es un dato del catálogo que la oferta necesita para
responder "quién dicta este grupo", y por eso vive en su propia tabla y no en `users`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.sqlalchemy.models.base import Base


class ProfessorModel(Base):
    """Docente que puede tener grupos asignados.

    Attributes:
        id: identificador único, generado por PostgreSQL con `gen_random_uuid()`.
        full_name: nombre completo tal como aparece en los registros institucionales.
        email: correo de contacto. Es opcional —hay docentes de cátedra sin correo
            institucional asignado— pero único cuando existe: PostgreSQL permite varios `NULL`
            bajo una restricción `UNIQUE`, así que la nulabilidad y la unicidad conviven.
        created_at: instante de creación del registro.
    """

    __tablename__ = "professors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        # `SET NULL` y no `CASCADE`: borrar la cuenta no puede llevarse el registro del docente,
        # al que apunta `course_offerings.professor_id`. Se pierde el acceso, no la historia.
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        # Único y PARCIAL. Único porque una cuenta no puede ser dos docentes a la vez: sin él,
        # `find_by_user_id` devolvería un resultado u otro según el plan de ejecución. Parcial
        # porque los `NULL` son la mayoría —casi ningún docente tiene cuenta— y no deben
        # competir entre sí ni ocupar índice.
        Index(
            "uq_professors_user_id",
            "user_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
    )
