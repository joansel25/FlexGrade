"""Modelo ORM de la tabla `programs`: el programa académico al que pertenece un estudiante.

Corresponde al DDL de `docs/DATA_MODEL.md` sección 2. Se declara en la Fase 1 —aunque el
catálogo académico completo llegue después— porque `students.program_id` es una clave foránea
obligatoria: sin `programs` no se puede crear la tabla `students`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Integer, String, func, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.sqlalchemy.models.base import Base


class ProgramModel(Base):
    """Programa académico ofrecido por la institución.

    Attributes:
        id: identificador único, generado por PostgreSQL con `gen_random_uuid()`.
        code: código institucional corto y único del programa (por ejemplo `ISIS`).
        name: nombre completo (por ejemplo `Ingeniería de Sistemas`).
        total_semesters: duración del plan de estudios. El `CHECK` impide valores no positivos.
        created_at: instante de creación del registro.
    """

    __tablename__ = "programs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    total_semesters: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        # Nombre corto: la convención lo expande a `ck_programs_total_semesters`.
        CheckConstraint("total_semesters > 0", name="total_semesters"),
    )
