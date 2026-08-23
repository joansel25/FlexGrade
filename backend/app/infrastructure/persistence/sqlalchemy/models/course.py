"""Modelo ORM de la tabla `courses`: la materia del catálogo académico.

Corresponde al DDL de `docs/DATA_MODEL.md` sección 2. Una materia es la unidad conceptual
(`Cálculo I`, 4 créditos); los grupos concretos que se dictan en un semestre son
`course_offerings`. Esa separación es la que permite ofrecer la misma materia en varios grupos
y en varios períodos sin duplicar su definición.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.sqlalchemy.models.base import Base


class CourseModel(Base):
    """Materia del catálogo, independiente del semestre en que se dicte.

    Attributes:
        id: identificador único, generado por PostgreSQL con `gen_random_uuid()`.
        code: código institucional corto y único de la materia (por ejemplo `MAT101`).
        name: nombre completo (por ejemplo `Cálculo I`).
        credits: créditos académicos. El `CHECK` impide valores no positivos.
        description: descripción del contenido. Opcional y sin longitud máxima: es texto libre
            de catálogo, no un dato sobre el que se filtre ni se indexe.
        created_at: instante de creación del registro.
    """

    __tablename__ = "courses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        # Nombre corto: la convención lo expande a `ck_courses_credits`.
        CheckConstraint("credits > 0", name="credits"),
        # `code` no lleva índice propio: su restricción UNIQUE ya lo cubre.
    )
