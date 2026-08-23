"""Modelo ORM de la tabla `schedule_blocks`: cada franja horaria de un grupo.

Corresponde al DDL de `docs/DATA_MODEL.md` sección 2. Un grupo que se dicta lunes y miércoles de
8 a 10 son dos filas, no una: modelarlo así es lo que permite que
`ScheduleConflictDetector` (Fase 3) compare franja contra franja para detectar choques de
horario, en vez de interpretar una cadena de texto tipo "LU-MI 8-10".
"""

from __future__ import annotations

import uuid
from datetime import time

from sqlalchemy import CheckConstraint, ForeignKey, Index, SmallInteger, String, Time, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.sqlalchemy.models.base import Base


class ScheduleBlockModel(Base):
    """Franja horaria semanal en la que se dicta un grupo.

    Attributes:
        id: identificador único, generado por PostgreSQL con `gen_random_uuid()`.
        course_offering_id: grupo al que pertenece la franja. `ON DELETE CASCADE`: un horario
            sin grupo no significa nada.
        day_of_week: día de la semana, de 1 (lunes) a 7 (domingo), según ISO 8601. El `CHECK`
            impide cualquier valor fuera de ese rango.
        start_time: hora de inicio, sin zona horaria: es una hora de calendario académico
            ("las ocho de la mañana"), no un instante absoluto.
        end_time: hora de fin. El `CHECK` garantiza que sea posterior al inicio.
        classroom: aula asignada. Opcional: se publica el horario antes de asignar espacios.
    """

    __tablename__ = "schedule_blocks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    course_offering_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course_offerings.id", ondelete="CASCADE"),
        nullable=False,
    )
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    classroom: Mapped[str | None] = mapped_column(String(50), nullable=True)

    __table_args__ = (
        # Nombres cortos: la convención los expande a `ck_schedule_blocks_<nombre>`.
        CheckConstraint("day_of_week BETWEEN 1 AND 7", name="day_of_week"),
        CheckConstraint("end_time > start_time", name="valid_time_range"),
        # Toda consulta de horario parte del grupo, y PostgreSQL no indexa el lado hijo de una
        # clave foránea automáticamente.
        Index("ix_schedule_offering", "course_offering_id"),
    )
