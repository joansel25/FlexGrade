"""Modelo ORM de la tabla `enrollments`: la inscripción de un estudiante en un grupo.

Corresponde al DDL de `docs/DATA_MODEL.md` sección 2. Es la tabla que registra el resultado de
la operación más sensible del sistema, y la que se escribe en la misma transacción que
descuenta el cupo de `course_offerings`.

La restricción `UNIQUE (student_id, course_offering_id, enrollment_period_id)` es la última
defensa contra la doble inscripción: aunque el caso de uso compruebe antes que el estudiante no
está ya inscrito, dos peticiones simultáneas del mismo estudiante podrían pasar esa
comprobación a la vez. PostgreSQL rechaza la segunda.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.sqlalchemy.models.base import Base


class EnrollmentModel(Base):
    """Inscripción de un estudiante en un grupo dentro de un período.

    Attributes:
        id: identificador único, generado por PostgreSQL con `gen_random_uuid()`.
        student_id: estudiante inscrito. Sin `ON DELETE`: PostgreSQL aplica `NO ACTION`, de
            modo que borrar un estudiante con inscripciones falla en vez de perder su
            historial académico en silencio.
        course_offering_id: grupo en el que se inscribió. Sin `ON DELETE` por la misma razón.
        enrollment_period_id: período en el que ocurrió. Es redundante —se podría deducir del
            grupo— pero se guarda a propósito: los reportes por período son la consulta más
            frecuente de la administración, y deducirlo obligaría a un `JOIN` en cada una.
        status: `ENROLLED`, `CANCELLED` o `WAITLISTED`. El último existe en el enum como
            preparación, pero la lógica de lista de espera es una ausencia intencional
            (`DATA_MODEL.md`).
        enrolled_at: instante de la inscripción.
        cancelled_at: instante de la cancelación, si la hubo.
        updated_at: instante de la última modificación, mantenido por el trigger
            `trg_enrollments_updated_at`.
    """

    __tablename__ = "enrollments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("students.id"),
        nullable=False,
    )
    course_offering_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course_offerings.id"),
        nullable=False,
    )
    enrollment_period_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("enrollment_periods.id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'ENROLLED'"),
    )
    enrolled_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    final_grade: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    graded_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        # Nombre corto: la convención lo expande a `ck_enrollments_status`.
        CheckConstraint(
            "status IN ('ENROLLED', 'CANCELLED', 'WAITLISTED')",
            name="status",
        ),
        # Un estudiante no puede inscribirse dos veces en el mismo grupo del mismo período.
        # Incluye las canceladas a propósito: reinscribirse tras cancelar reactiva la fila
        # existente en vez de crear una segunda, y así el historial no se duplica.
        UniqueConstraint(
            "student_id",
            "course_offering_id",
            "enrollment_period_id",
            name="uq_enrollments_student_offering_period",
        ),
        # Índices con nombre explícito, según el DDL de `docs/DATA_MODEL.md`.
        Index("ix_enrollments_offering", "course_offering_id"),
        Index("ix_enrollments_period", "enrollment_period_id"),
        # La nota, en su escala. Red final con la misma filosofía que el control de cupos:
        # `Grade` da el mensaje útil y esto impide que entre por cualquier otro camino.
        CheckConstraint(
            "final_grade IS NULL OR (final_grade >= 0 AND final_grade <= 5)",
            name="final_grade_range",
        ),
        # La nota y su instante van juntas o no van: una nota sin fecha no dice cuándo se puso,
        # y una fecha sin nota no significa nada.
        CheckConstraint("(final_grade IS NULL) = (graded_at IS NULL)", name="graded_at_with_grade"),
        # Lo que falta por calificar. Es la consulta que la 9.3 ejecuta antes de consolidar.
        # Parcial porque al final del semestre casi todas están calificadas.
        Index(
            "ix_enrollments_pending_grade",
            "enrollment_period_id",
            postgresql_where=text("final_grade IS NULL AND status = 'ENROLLED'"),
        ),
        # Índice PARCIAL de las inscripciones activas de un estudiante. Resuelve la consulta
        # que el caso de uso ejecuta en CADA intento de inscripción durante el pico: «qué
        # tiene inscrito ahora esta persona», necesaria para detectar choques de horario y
        # dobles inscripciones.
        #
        # DESVIACIÓN DEL DDL de `docs/DATA_MODEL.md`, que lo declara sobre `status`. Un índice
        # sobre esa columna, filtrado además por `status = 'ENROLLED'`, contendría millones de
        # filas con la MISMA clave: no discrimina nada y PostgreSQL apenas lo usaría. La
        # columna que discrimina es `student_id`. El filtro parcial se mantiene porque las
        # canceladas se acumulan con los semestres y nunca interesan aquí.
        Index(
            "ix_enrollments_active",
            "student_id",
            postgresql_where=text("status = 'ENROLLED'"),
        ),
        # `student_id` no lleva además un índice completo propio: es la primera columna de la
        # restricción UNIQUE, cuyo índice ya cubre el filtro por estudiante sin el parcial.
    )
