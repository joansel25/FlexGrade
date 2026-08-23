"""auth: usuarios, programas, estudiantes y administradores

Primera migracion con contenido. Crea las cuatro tablas que sostienen la Fase 1
(autenticacion), tal como estan descritas en el DDL de `docs/DATA_MODEL.md`
seccion 2: `users`, `programs`, `students` y `administrators`.

`programs` se crea en esta fase aunque el catalogo academico llegue despues,
porque `students.program_id` es una clave foranea obligatoria y sin la tabla
referenciada no se puede crear `students`.

Partio de `alembic revision --autogenerate` y se corrigio a mano en dos puntos
que autogenerate no cubre:

1. La extension `pgcrypto`, que provee `gen_random_uuid()`. Autogenerate solo
   compara tablas, indices y restricciones: no ve las extensiones. Se crea antes
   que cualquier tabla porque los `DEFAULT` de las claves primarias la usan.
2. El `downgrade()`, que autogenerate genera pero conviene revisar: el orden de
   borrado va de hija a padre para no violar las claves foraneas.

Los nombres de restriccion van envueltos en `op.f()`, que no es decorativo:
marca el nombre como definitivo. Sin el, Alembic lo trata como un token y le
vuelve a aplicar la `naming_convention` de `Base.metadata`, produciendo
aberraciones como `ck_users_ck_users_role`.

Revision ID: 0002_auth_tables
Revises: 0001_baseline
Create Date: 2026-08-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_auth_tables"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea la extension pgcrypto y las cuatro tablas de autenticacion y perfiles."""
    # `gen_random_uuid()` proviene de pgcrypto. `IF NOT EXISTS` hace la sentencia
    # idempotente: un entorno donde la extension ya este instalada no falla.
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # Orden de creacion de padre a hija: `students` referencia a `programs` y a `users`.
    op.create_table(
        "programs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("total_semesters", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("total_semesters > 0", name=op.f("ck_programs_total_semesters")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_programs")),
        sa.UniqueConstraint("code", name=op.f("uq_programs_code")),
    )

    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # El rol se restringe en la base de datos, no solo en la aplicacion: es la
        # ultima defensa contra un valor desconocido llegado por cualquier via.
        sa.CheckConstraint("role IN ('STUDENT', 'ADMIN')", name=op.f("ck_users_role")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_index("idx_users_email", "users", ["email"], unique=False)

    op.create_table(
        "administrators",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_administrators_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_administrators")),
        sa.UniqueConstraint("user_id", name=op.f("uq_administrators_user_id")),
    )

    op.create_table(
        "students",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_code", sa.String(length=20), nullable=False),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("current_semester", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("enrollment_date", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("current_semester >= 1", name=op.f("ck_students_current_semester")),
        # Sin `ondelete`: PostgreSQL aplica NO ACTION, de modo que borrar un programa
        # con estudiantes falla en vez de arrastrarlos en cascada.
        sa.ForeignKeyConstraint(
            ["program_id"],
            ["programs.id"],
            name=op.f("fk_students_program_id_programs"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_students_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_students")),
        sa.UniqueConstraint("student_code", name=op.f("uq_students_student_code")),
        sa.UniqueConstraint("user_id", name=op.f("uq_students_user_id")),
    )
    op.create_index("idx_students_code", "students", ["student_code"], unique=False)
    op.create_index("idx_students_program", "students", ["program_id"], unique=False)


def downgrade() -> None:
    """Elimina las cuatro tablas, de hija a padre para respetar las claves foraneas."""
    op.drop_index("idx_students_program", table_name="students")
    op.drop_index("idx_students_code", table_name="students")
    op.drop_table("students")
    op.drop_table("administrators")
    op.drop_index("idx_users_email", table_name="users")
    op.drop_table("users")
    op.drop_table("programs")

    # La extension `pgcrypto` NO se elimina a proposito. Es un objeto compartido a
    # nivel de base de datos: otros esquemas u objetos pueden depender de ella, y en
    # RDS su instalacion puede requerir privilegios de los que la cuenta de la
    # aplicacion no dispone. Dejarla instalada es inocuo y `CREATE EXTENSION IF NOT
    # EXISTS` hace que el `upgrade` posterior vuelva a funcionar sin cambios.
