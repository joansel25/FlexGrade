"""Modelo ORM de la tabla `program_courses`: el plan de estudios de cada programa.

Corresponde al DDL de `docs/DATA_MODEL.md` sección 2. Es la tabla de asociación entre
`programs` y `courses`, con dos atributos propios de la relación —en qué semestre se sugiere
la materia y si es obligatoria— que no pertenecen ni al programa ni a la materia por separado:
`Cálculo I` puede ser de segundo semestre y obligatoria en Ingeniería, y electiva en Derecho.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.sqlalchemy.models.base import Base


class ProgramCourseModel(Base):
    """Materia que forma parte del plan de estudios de un programa.

    La clave primaria es compuesta por las dos claves foráneas: una materia aparece como mucho
    una vez en el plan de un programa, y esa regla la impone la base de datos, no el código.

    Attributes:
        program_id: programa al que pertenece el plan. `ON DELETE CASCADE`: si el programa
            desaparece, su plan de estudios no tiene sentido por separado.
        course_id: materia incluida en el plan. `ON DELETE CASCADE` por la misma razón.
        suggested_semester: semestre en el que el plan sugiere cursarla; nunca inferior a 1.
            Es una sugerencia, no una restricción: quien decide si el estudiante puede
            inscribirla son los prerrequisitos.
        is_mandatory: si es obligatoria para graduarse o electiva.
    """

    __tablename__ = "program_courses"

    program_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("programs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    suggested_semester: Mapped[int] = mapped_column(Integer, nullable=False)
    is_mandatory: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )

    __table_args__ = (
        # Nombre corto: la convención lo expande a `ck_program_courses_suggested_semester`.
        CheckConstraint("suggested_semester >= 1", name="suggested_semester"),
        # No hace falta índice sobre `program_id`: es la primera columna de la clave primaria
        # compuesta, así que el índice de la PK ya sirve para filtrar por programa.
    )
