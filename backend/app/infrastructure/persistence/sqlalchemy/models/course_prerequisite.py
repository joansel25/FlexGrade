"""Modelo ORM de la tabla `course_prerequisites`: qué materia exige haber aprobado cuál.

Corresponde al DDL de `docs/DATA_MODEL.md` sección 2. Es una relación autoreferente sobre
`courses`: la fila `(MAT102, MAT101)` significa "para ver Cálculo II hay que haber aprobado
Cálculo I". La validación real la hará `PrerequisiteValidator` en la Fase 3, cruzando estas
filas contra `academic_history` con `status = 'APPROVED'`.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.sqlalchemy.models.base import Base


class CoursePrerequisiteModel(Base):
    """Prerrequisito de una materia sobre otra.

    Attributes:
        course_id: la materia que impone el requisito. `ON DELETE CASCADE`: si la materia se
            elimina del catálogo, sus prerrequisitos dejan de existir con ella.
        required_course_id: la materia que hay que haber aprobado antes.

    El `CHECK` impide que una materia se exija a sí misma, que sería un requisito imposible de
    cumplir y dejaría la materia permanentemente ininscribible. No detecta ciclos más largos
    (A exige B, B exige A): eso requeriría un recorrido de grafo que ninguna restricción
    declarativa de PostgreSQL puede expresar, y se valida al cargar el catálogo.
    """

    __tablename__ = "course_prerequisites"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    required_course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        primary_key=True,
    )

    __table_args__ = (
        # Nombre corto: la convención lo expande a `ck_course_prerequisites_no_self_reference`.
        CheckConstraint("course_id <> required_course_id", name="no_self_reference"),
    )
