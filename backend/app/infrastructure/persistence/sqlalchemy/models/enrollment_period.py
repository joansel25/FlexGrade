"""Modelo ORM de la tabla `enrollment_periods`: la ventana de matrícula.

Corresponde al DDL de `docs/DATA_MODEL.md` sección 2. Es la tabla que delimita *cuándo* se
puede inscribir: fuera de la ventana activa, el caso de uso de inscripción rechaza la petición.
Todo el requisito no funcional del sistema —5.000 estudiantes concurrentes— ocurre dentro de
las pocas horas que dura una de estas filas.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Index, String, func, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.sqlalchemy.models.base import Base


class EnrollmentPeriodModel(Base):
    """Ventana temporal durante la cual se permite matricularse.

    Attributes:
        id: identificador único, generado por PostgreSQL con `gen_random_uuid()`.
        code: código único de la ventana (por ejemplo `2025-2-V1`, primera vuelta de 2025-2).
        academic_period: semestre académico al que pertenece (por ejemplo `2025-2`). Varias
            ventanas —primera vuelta, ajustes, adiciones— comparten el mismo semestre, y por eso
            este campo no es único mientras que `code` sí lo es.
        name: nombre legible para mostrar al estudiante.
        starts_at: instante de apertura.
        ends_at: instante de cierre. El `CHECK` garantiza que sea posterior a la apertura.
        is_active: si es la ventana vigente. La activación es una operación administrativa
            explícita (`PUT /admin/enrollment-periods/{id}/activate`), no algo que se deduzca
            de las fechas: permite dejar un período preparado con antelación sin abrirlo.
        created_at: instante de creación del registro.
    """

    __tablename__ = "enrollment_periods"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    academic_period: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        # Nombre corto: la convención lo expande a `ck_enrollment_periods_valid_range`.
        CheckConstraint("ends_at > starts_at", name="valid_range"),
        # Índice PARCIAL. La consulta que importa es "dame el período activo", que se ejecuta
        # en casi cada petición de catálogo e inscripción. Un índice sobre toda la columna
        # sería casi inútil (solo dos valores distintos, y millones de filas apuntando a
        # `false` con el tiempo); el parcial indexa únicamente las contadas filas activas, así
        # que ocupa unos pocos bytes y resuelve esa consulta al instante.
        Index(
            "ix_enrollment_periods_active",
            "is_active",
            postgresql_where=text("is_active = true"),
        ),
    )
