"""enrollment: inscripciones e historial academico

Cierra el esquema del sistema con las dos ultimas tablas de `docs/DATA_MODEL.md` seccion 2:
`enrollments`, que registra el resultado de la operacion mas sensible del sistema, y
`academic_history`, que es la fuente de verdad de la validacion de prerrequisitos.

`enrollments` se escribe en la MISMA transaccion que descuenta el cupo de `course_offerings`.
Esa atomicidad es lo que impide el estado imposible de «cupo descontado sin inscripcion» o su
contrario, y la garantiza el UnitOfWork de la iteracion 3.2.

Partio de `alembic revision --autogenerate` y se corrigio a mano en tres puntos:

1. El trigger `trg_enrollments_updated_at`. Autogenerate compara tablas, indices y
   restricciones, pero NO ve triggers. Sin el, `updated_at` se quedaria congelada tras el
   INSERT justo en la tabla donde importa, porque cambia en cada cancelacion. Reutiliza la
   funcion compartida `set_updated_at()` que creo la migracion 0003.
2. El identificador de la revision, alineado con la numeracion `000N_` del proyecto.
3. Dos desviaciones del DDL documentado, ambas sobre indices que como estan escritos no
   servirian para nada (ver abajo). `DATA_MODEL.md` queda actualizado con el motivo.

DESVIACIONES DEL DDL, Y POR QUE:

- `ix_enrollments_active` se declara sobre `student_id` y no sobre `status`. Un indice sobre
  `status` filtrado ademas por `status = 'ENROLLED'` contendria millones de filas con la MISMA
  clave: no discrimina nada. La columna que discrimina es `student_id`, y la consulta real que
  corre en cada intento de inscripcion es «que tiene inscrito ahora esta persona». El filtro
  parcial se mantiene porque las canceladas se acumulan con los semestres y nunca interesan
  para esa pregunta.
- `ix_history_student` no se crea. Es identico al prefijo del indice que PostgreSQL genera
  para `uq_academic_history_student_course_period`, asi que seria un duplicado exacto: coste de
  escritura y de espacio sin ninguna ganancia. Es el mismo defecto que corrigio la migracion
  0003 para `users` y `students`. `ix_history_student_status` si se crea: la restriccion UNIQUE
  no puede resolver un filtro por `(student_id, status)` mas alla del primer campo.

Revision ID: 0006_enrollment_tables
Revises: 0005_unaccent_search
Create Date: 2026-08-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_enrollment_tables"
down_revision: str | None = "0005_unaccent_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea las dos tablas y el trigger de `updated_at` de las inscripciones."""
    # Orden de padre a hija: ambas referencian a `students`, `courses`, `course_offerings` y
    # `enrollment_periods`, que ya existen desde las migraciones 0002 y 0004.
    op.create_table(
        "academic_history",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("course_id", sa.UUID(), nullable=False),
        sa.Column("academic_period", sa.String(length=20), nullable=False),
        sa.Column("final_grade", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('APPROVED', 'FAILED', 'WITHDRAWN')", name=op.f("ck_academic_history_status")
        ),
        sa.CheckConstraint(
            "final_grade BETWEEN 0.0 AND 5.0", name=op.f("ck_academic_history_final_grade_range")
        ),
        sa.ForeignKeyConstraint(
            ["course_id"], ["courses.id"], name=op.f("fk_academic_history_course_id_courses")
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name=op.f("fk_academic_history_student_id_students"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_academic_history")),
        sa.UniqueConstraint(
            "student_id",
            "course_id",
            "academic_period",
            name="uq_academic_history_student_course_period",
        ),
    )
    op.create_index(
        "ix_history_student_status", "academic_history", ["student_id", "status"], unique=False
    )
    op.create_table(
        "enrollments",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("course_offering_id", sa.UUID(), nullable=False),
        sa.Column("enrollment_period_id", sa.UUID(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'ENROLLED'"), nullable=False
        ),
        sa.Column(
            "enrolled_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("cancelled_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('ENROLLED', 'CANCELLED', 'WAITLISTED')", name=op.f("ck_enrollments_status")
        ),
        sa.ForeignKeyConstraint(
            ["course_offering_id"],
            ["course_offerings.id"],
            name=op.f("fk_enrollments_course_offering_id_course_offerings"),
        ),
        sa.ForeignKeyConstraint(
            ["enrollment_period_id"],
            ["enrollment_periods.id"],
            name=op.f("fk_enrollments_enrollment_period_id_enrollment_periods"),
        ),
        sa.ForeignKeyConstraint(
            ["student_id"], ["students.id"], name=op.f("fk_enrollments_student_id_students")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_enrollments")),
        sa.UniqueConstraint(
            "student_id",
            "course_offering_id",
            "enrollment_period_id",
            name="uq_enrollments_student_offering_period",
        ),
    )
    op.create_index(
        "ix_enrollments_active",
        "enrollments",
        ["student_id"],
        unique=False,
        postgresql_where=sa.text("status = 'ENROLLED'"),
    )
    op.create_index("ix_enrollments_offering", "enrollments", ["course_offering_id"], unique=False)
    op.create_index("ix_enrollments_period", "enrollments", ["enrollment_period_id"], unique=False)

    # --- Auditoria temporal de la unica tabla nueva que muta -----------------
    # `enrollments.status` y `cancelled_at` cambian al cancelar, asi que `updated_at` tiene
    # que mantenerse sola. `academic_history` no lo necesita: es un registro historico que se
    # escribe una vez (DATA_MODEL.md, "Auditoria temporal").
    op.execute(
        """
        CREATE TRIGGER trg_enrollments_updated_at
            BEFORE UPDATE ON enrollments
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """
    )


def downgrade() -> None:
    """Elimina el trigger y las dos tablas, de hija a padre."""
    op.execute("DROP TRIGGER IF EXISTS trg_enrollments_updated_at ON enrollments")

    op.drop_index("ix_enrollments_period", table_name="enrollments")
    op.drop_index("ix_enrollments_offering", table_name="enrollments")
    op.drop_index(
        "ix_enrollments_active",
        table_name="enrollments",
        postgresql_where=sa.text("status = 'ENROLLED'"),
    )
    op.drop_table("enrollments")
    op.drop_index("ix_history_student_status", table_name="academic_history")
    op.drop_table("academic_history")
