"""El docente pasa a ser un usuario del sistema.

Hasta ahora `professors` era solo un dato del catálogo: quién dicta este grupo. La Fase 9 lo
convierte en actor, porque quien tiene las notas es quien dicta la clase, y el único camino
alternativo —que Registro Académico las teclee todas— concentra el trabajo justo donde no está
la información.

DOS DECISIONES DEL ESQUEMA, ninguna cosmética:

`professors.user_id` es NULLABLE. Un docente existe como dato del catálogo antes de tener cuenta:
los diez que siembra `seed.py` se crearon así, y un grupo puede tener docente asignado desde el
día en que se abre aunque su cuenta se cree semanas después. Hacerlo obligatorio exigiría inventar
una cuenta por cada nombre.

`ON DELETE SET NULL` y no `CASCADE`. Borrar una cuenta no puede llevarse por delante el registro
del docente: `course_offerings.professor_id` lo apunta, y con `CASCADE` desaparecería el docente
de grupos que ya se dictaron. Se pierde el acceso, no la historia.

El `CHECK` de `users.role` se recrea con el valor nuevo. Recrearlo es un `ALTER TABLE` normal,
que es exactamente por lo que la 6.2 eligió `CHECK` sobre un `ENUM` de PostgreSQL: añadir un
valor a un `ENUM` obliga a un `ALTER TYPE` que no se puede revertir en la misma migración.

Revision ID: 0011_professor_accounts
Revises: 0010_no_double_booking
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0011_professor_accounts"
down_revision = "0010_no_double_booking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("professors", sa.Column("user_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_professors_user_id_users",
        "professors",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # Índice ÚNICO y parcial. Único porque una cuenta no puede ser dos docentes a la vez: sin
    # esto, `find_by_user_id` devolvería un resultado u otro según el orden del plan de
    # ejecución. Parcial porque los `NULL` no deben competir entre sí, y son la mayoría: un
    # índice único normal en PostgreSQL ya los admite repetidos, pero el parcial además no los
    # almacena.
    op.create_index(
        "uq_professors_user_id",
        "professors",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )

    # `find_by_professor` filtra por las dos columnas y ninguna de las dos es prefijo de un
    # índice existente: `ix_offerings_period` empieza por el período. Es la consulta que se
    # ejecuta cada vez que un docente entra.
    op.create_index(
        "ix_offerings_professor",
        "course_offerings",
        ["professor_id", "enrollment_period_id"],
    )

    op.drop_constraint("role", "users", type_="check")
    op.create_check_constraint(
        "role", "users", "role IN ('STUDENT', 'ADMIN', 'PROFESSOR')"
    )


def downgrade() -> None:
    # Las cuentas de docente quedarían con un rol que el CHECK anterior no admite, así que hay
    # que decidir qué hacer con ellas antes de recrearlo. Se desactivan en vez de borrarse: la
    # cuenta puede tener notas registradas a su nombre, y borrarla perdería esa trazabilidad.
    op.execute(
        "UPDATE users SET role = 'STUDENT', is_active = false WHERE role = 'PROFESSOR'"
    )

    op.drop_constraint("role", "users", type_="check")
    op.create_check_constraint("role", "users", "role IN ('STUDENT', 'ADMIN')")

    op.drop_index("ix_offerings_professor", table_name="course_offerings")
    op.drop_index("uq_professors_user_id", table_name="professors")
    op.drop_constraint("fk_professors_user_id_users", "professors", type_="foreignkey")
    op.drop_column("professors", "user_id")
