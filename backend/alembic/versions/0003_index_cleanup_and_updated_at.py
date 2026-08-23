"""indices: limpieza y prefijo ix_; auditoria temporal con trigger de updated_at

Corrige tres defectos detectados en el esquema durante la Fase 1 y documentados
en DATA_MODEL.md ("Auditoria temporal") y BEST_PRACTICES.md ("Convenciones de
base de datos"):

1. Indices redundantes sobre columnas que ya tienen UNIQUE. PostgreSQL crea un
   indice B-tree al imponer la restriccion, asi que el indice manual era un
   duplicado exacto: coste de escritura y de espacio sin ninguna ganancia en
   lectura.
2. Prefijo de indices unificado a ``ix_``, que es lo que genera la
   ``naming_convention`` del MetaData de SQLAlchemy y lo que produce
   ``alembic revision --autogenerate``.
3. ``updated_at`` no se mantenia sola: ``DEFAULT NOW()`` solo cubre el INSERT.
   Se introduce la funcion compartida ``set_updated_at()`` y su trigger
   BEFORE UPDATE.

ALCANCE: solo se tocan las tablas que existen hoy (Fase 1). Las columnas
``updated_at`` de ``course_offerings`` y ``enrollments``, y el renombrado de sus
indices, se aplicaran en las migraciones que creen esas tablas (Fases 2 y 3), ya
correctos de origen gracias a los documentos actualizados. La funcion
``set_updated_at()`` queda disponible desde ahora: esas migraciones solo tendran
que anadir su ``CREATE TRIGGER``.

Revision ID: 0003_index_cleanup
Revises: 0002_auth_tables
Create Date: 2026-08-22
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_index_cleanup"
down_revision: str | None = "0002_auth_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tablas que hoy tienen columna `updated_at`. Cuando las Fases 2 y 3 creen
# `course_offerings` y `enrollments`, sus migraciones anaden el trigger
# correspondiente reutilizando la misma funcion.
TABLAS_CON_UPDATED_AT: tuple[str, ...] = ("users",)


def upgrade() -> None:
    # --- 1. Indices redundantes: los cubre la restriccion UNIQUE ------------
    op.drop_index("idx_users_email", table_name="users")
    op.drop_index("idx_students_code", table_name="students")

    # --- 2. Unificacion del prefijo idx_ -> ix_ -----------------------------
    # ALTER INDEX ... RENAME conserva el indice: no lo reconstruye, por lo que
    # no bloquea escrituras de forma prolongada ni pierde estadisticas.
    op.execute("ALTER INDEX idx_students_program RENAME TO ix_students_program")

    # --- 3. Auditoria temporal ---------------------------------------------
    # Funcion compartida por todas las tablas con `updated_at`. `CREATE OR
    # REPLACE` la hace idempotente.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    for tabla in TABLAS_CON_UPDATED_AT:
        op.execute(
            f"""
            CREATE TRIGGER trg_{tabla}_updated_at
                BEFORE UPDATE ON {tabla}
                FOR EACH ROW EXECUTE FUNCTION set_updated_at();
            """
        )


def downgrade() -> None:
    # Orden inverso: primero los triggers, despues la funcion de la que dependen.
    for tabla in TABLAS_CON_UPDATED_AT:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{tabla}_updated_at ON {tabla}")

    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")

    op.execute("ALTER INDEX ix_students_program RENAME TO idx_students_program")

    op.create_index("idx_students_code", "students", ["student_code"])
    op.create_index("idx_users_email", "users", ["email"])
