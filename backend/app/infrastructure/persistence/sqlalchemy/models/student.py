"""Modelo ORM de la tabla `students`: el perfil académico del estudiante.

Corresponde al DDL de `docs/DATA_MODEL.md` sección 2. Separa el perfil de la cuenta: `users`
autentica, `students` describe. La relación con `users` es 1:1 y se garantiza con `UNIQUE` sobre
`user_id`.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.sqlalchemy.models.base import Base


class StudentModel(Base):
    """Perfil académico asociado a una cuenta de usuario con rol `STUDENT`.

    Attributes:
        id: identificador único, generado por PostgreSQL con `gen_random_uuid()`.
        user_id: cuenta de autenticación asociada. `ON DELETE CASCADE`: si la cuenta desaparece,
            el perfil no tiene sentido y se elimina con ella.
        student_code: código institucional del estudiante, único en toda la institución.
        program_id: programa al que pertenece. Sin `ON DELETE`: PostgreSQL aplica `NO ACTION`,
            de modo que borrar un programa con estudiantes matriculados falla en vez de dejar
            perfiles huérfanos o borrarlos en cascada silenciosamente.
        current_semester: semestre que cursa actualmente; nunca inferior a 1.
        full_name: nombre completo tal como aparece en los registros institucionales.
        enrollment_date: fecha de ingreso a la institución.
        created_at: instante de creación del registro.
    """

    __tablename__ = "students"

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
    student_code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    program_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("programs.id"),
        nullable=False,
    )
    current_semester: Mapped[int] = mapped_column(Integer, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    enrollment_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        # Nombre corto: la convención lo expande a `ck_students_current_semester`.
        CheckConstraint("current_semester >= 1", name="current_semester"),
        # `program_id` es clave foránea de alta frecuencia (listados por programa) y PostgreSQL
        # no indexa el lado hijo de una FK automáticamente.
        Index("ix_students_program", "program_id"),
        # `student_code` no lleva indice propio: su restriccion UNIQUE ya lo cubre.
    )
