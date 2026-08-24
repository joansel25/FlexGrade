"""Modelo ORM de la tabla `academic_history`: lo que el estudiante ya cursó.

Corresponde al DDL de `docs/DATA_MODEL.md` sección 2. Es la fuente de verdad de la validación
de prerrequisitos: para saber si alguien puede inscribir Cálculo II hay que comprobar que tiene
Cálculo I con `status = 'APPROVED'` en esta tabla.

Guarda el resultado de semestres ya cerrados, no del actual: lo que se está cursando ahora vive
en `enrollments`. Separar ambos es lo que permite que un estudiante inscriba una materia sin
que eso cuente como aprobada.
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


class AcademicHistoryModel(Base):
    """Registro de una materia ya cursada por un estudiante.

    Attributes:
        id: identificador único, generado por PostgreSQL con `gen_random_uuid()`.
        student_id: estudiante al que pertenece. `ON DELETE CASCADE`: el historial no tiene
            sentido sin la persona.
        course_id: materia cursada. Sin `ON DELETE`: borrar una materia que aparece en algún
            historial falla, porque eso reescribiría el pasado académico de alguien.
        academic_period: semestre en que se cursó (por ejemplo `2024-2`). Es texto y no una
            clave foránea a `enrollment_periods` a propósito: el historial puede incluir
            semestres anteriores a la puesta en marcha del sistema, o materias homologadas de
            otra institución, para los que no existe ninguna fila de período.
        final_grade: nota definitiva, entre 0.0 y 5.0. Opcional: una materia retirada no tiene
            nota. Se usa `Numeric` y no `float` porque una nota es un valor exacto con dos
            decimales, y la aritmética binaria de coma flotante introduce errores de redondeo
            inaceptables en un dato académico.
        status: `APPROVED`, `FAILED` o `WITHDRAWN`. Solo `APPROVED` cuenta como prerrequisito
            cumplido.
        created_at: instante de creación del registro.
    """

    __tablename__ = "academic_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id"),
        nullable=False,
    )
    academic_period: Mapped[str] = mapped_column(String(20), nullable=False)
    final_grade: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        # Nombres cortos: la convención los expande a `ck_academic_history_<nombre>`.
        CheckConstraint("final_grade BETWEEN 0.0 AND 5.0", name="final_grade_range"),
        CheckConstraint(
            "status IN ('APPROVED', 'FAILED', 'WITHDRAWN')",
            name="status",
        ),
        # Una materia aparece como mucho una vez por estudiante y semestre. Si se repite tras
        # perderla, es otro `academic_period` y por tanto otra fila: el historial conserva
        # ambos intentos, que es lo que un expediente académico debe hacer.
        UniqueConstraint(
            "student_id",
            "course_id",
            "academic_period",
            name="uq_academic_history_student_course_period",
        ),
        # `ix_history_student` no se declara: es el prefijo de la restricción UNIQUE, cuyo
        # índice ya cubre el filtro por estudiante.
        #
        # Este otro sí, porque la validación de prerrequisitos filtra SIEMPRE por las dos
        # columnas a la vez —«qué aprobó este estudiante»— y es la consulta que corre en cada
        # intento de inscripción durante el pico.
        Index("ix_history_student_status", "student_id", "status"),
    )
