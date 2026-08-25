"""Modelo ORM de `program_course_requirements`: qué exige una materia dentro de una carrera.

Sustituye a la antigua `course_prerequisites`, que relacionaba materia con materia. El cambio
no es de forma sino de significado: un requisito académico pertenece al **plan de estudios**,
no al catálogo. `FIS101` puede exigir `MAT101` en Ingeniería y entrar como electiva sin nada
que exigir en otro programa, y con la tabla anterior esas dos verdades no cabían a la vez.

La fila `(ISIS, FIS101, MAT101, COREQUISITE)` significa «en el plan de Ingeniería, para ver
Física I hay que estar cursando Cálculo I al mismo tiempo».
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, String, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.sqlalchemy.models.base import Base


class ProgramCourseRequirementModel(Base):
    """Requisito de una materia sobre otra dentro del plan de estudios de un programa.

    Attributes:
        program_id: plan de estudios en el que rige el requisito.
        course_id: la materia que impone el requisito.
        required_course_id: la materia exigida.
        requirement_type: `PREREQUISITE` (aprobada antes) o `COREQUISITE` (cursada a la vez).
        created_at: instante en que se cargó el requisito.

    LA CLAVE PRIMARIA NO INCLUYE EL TIPO. Es deliberado: con `(program_id, course_id,
    required_course_id)` como clave, la base impide que la misma pareja exista dos veces con
    tipos distintos. Incluir el tipo permitiría declarar que `MAT101` es a la vez prerrequisito
    y correquisito de `FIS101`, dos reglas que se contradicen —una exige haberla terminado, la
    otra exige estar cursándola— y que dejarían la materia ininscribible sin que nada avisara.

    LAS CLAVES FORÁNEAS APUNTAN A `program_courses`, NO A `courses`. Son compuestas, sobre
    `(program_id, course_id)`, y esa elección hace imposible por construcción el error más
    probable al cargar un plan: exigir una materia que no pertenece a esa carrera. Con claves
    sueltas hacia `courses`, nada impediría que el plan de Derecho exigiera Programación II, y
    el estudiante se encontraría con un requisito que no puede cursar jamás. `ON DELETE
    CASCADE`: sacar una materia del plan se lleva con ella los requisitos en los que aparece.

    ÍNDICES. Las consultas que filtran por `(program_id, course_id)` —los requisitos de una
    materia, y los de la materia exigida al comprobar si el correquisito es mutuo— las resuelve
    el índice de la clave primaria, porque esas dos columnas son su prefijo.

    La consulta INVERSA no. `find_corequisite_dependents` pregunta «qué materias exigen a esta»
    y filtra por `(program_id, required_course_id)`, que no es prefijo de la PK, así que lleva
    índice propio (`ix_program_course_requirements_required`, migración `0008`). Sostiene la
    regla de cancelación, que corre dentro de una transacción que libera un cupo mientras las
    inscripciones compiten por él: el peor sitio posible para un recorrido de tabla.
    """

    __tablename__ = "program_course_requirements"

    program_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    required_course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    requirement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    __table_args__ = (
        # Nombres cortos: la convención de `base.py` los expande con la tabla delante.
        CheckConstraint("course_id <> required_course_id", name="no_self_reference"),
        # El tipo se valida con un CHECK y no con un ENUM de PostgreSQL, igual que
        # `enrollments.status`: añadir un valor a un ENUM obliga a un `ALTER TYPE` que no se
        # puede revertir en la misma migración, y un CHECK se cambia con un `ALTER TABLE`
        # normal. El conjunto cerrado lo garantizan igual los dos.
        CheckConstraint(
            "requirement_type IN ('PREREQUISITE', 'COREQUISITE')",
            name="requirement_type",
        ),
        ForeignKeyConstraint(
            ["program_id", "course_id"],
            ["program_courses.program_id", "program_courses.course_id"],
            # Nombre explícito y corto. La convención de `base.py` compondría
            # `fk_program_course_requirements_program_id_course_id_program_courses`, que pasa
            # de los 63 caracteres que admite un identificador de PostgreSQL: la base lo
            # truncaría y dejaría de coincidir con el que espera la migración.
            name="fk_pcr_course_in_plan",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["program_id", "required_course_id"],
            ["program_courses.program_id", "program_courses.course_id"],
            name="fk_pcr_required_course_in_plan",
            ondelete="CASCADE",
        ),
        # Nombre explícito y corto: la convención compondría uno de más de 63 caracteres, que
        # PostgreSQL truncaría, y el nombre dejaría de coincidir con el de la migración.
        Index("ix_program_course_requirements_required", "program_id", "required_course_id"),
    )
