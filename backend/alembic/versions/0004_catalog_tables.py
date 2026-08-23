"""catalog: profesores, materias, planes, prerrequisitos, periodos, ofertas y horarios

Crea las siete tablas del catalogo academico y de la oferta del semestre que sostienen
la Fase 2, tal como estan descritas en el DDL de `docs/DATA_MODEL.md` seccion 2:
`professors`, `courses`, `program_courses`, `course_prerequisites`, `enrollment_periods`,
`course_offerings` y `schedule_blocks`.

`course_offerings` merece una nota aparte. Es la tabla sobre la que se descuenta el cupo
durante la ventana de matricula, y dos de sus elementos son los que hacen imposible el
sobrecupo (CLAUDE.md, "El mecanismo que sostiene el requisito no funcional central"):

- la columna `version`, que soporta el bloqueo optimista del UPDATE de inscripcion, y
- el `CHECK (enrolled_count <= total_capacity)`, la red de seguridad que PostgreSQL aplica
  aunque el bloqueo optimista fallara.

Ambos se crean aqui, aunque la logica que los usa llegue en la Fase 3: el esquema tiene que
estar bien desde el primer INSERT, no desde que exista el caso de uso.

Partio de `alembic revision --autogenerate` y se corrigio a mano en dos puntos que
autogenerate no cubre:

1. El trigger `trg_course_offerings_updated_at`. Autogenerate compara tablas, indices y
   restricciones, pero NO ve triggers. Sin el, `updated_at` solo se rellenaria en el INSERT
   por su `DEFAULT NOW()` y se quedaria congelada en cada UPDATE posterior, que es justo
   cuando ese dato importa: cada descuento de cupo. Reutiliza la funcion compartida
   `set_updated_at()` que creo la migracion 0003.
2. El identificador de la revision, alineado con la numeracion `000N_` del proyecto en vez
   del hash aleatorio que genera Alembic.

Revision ID: 0004_catalog_tables
Revises: 0003_index_cleanup
Create Date: 2026-08-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_catalog_tables"
down_revision: str | None = "0003_index_cleanup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea las siete tablas del catalogo y el trigger de `updated_at` de las ofertas."""
    # Orden de creacion de padre a hija: `course_offerings` referencia a `courses`,
    # `enrollment_periods` y `professors`, y `schedule_blocks` referencia a `course_offerings`.
    op.create_table(
        "courses",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("credits > 0", name=op.f("ck_courses_credits")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_courses")),
        sa.UniqueConstraint("code", name=op.f("uq_courses_code")),
    )

    op.create_table(
        "enrollment_periods",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("academic_period", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("starts_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("ends_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("ends_at > starts_at", name=op.f("ck_enrollment_periods_valid_range")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_enrollment_periods")),
        sa.UniqueConstraint("code", name=op.f("uq_enrollment_periods_code")),
    )
    # Indice PARCIAL y UNICO. Hace dos trabajos con una sola estructura:
    #
    # 1. Acelera la consulta "dame el periodo activo", que corre en casi cada peticion de
    #    catalogo y en cada intento de inscripcion. Al indexar solo las filas activas ocupa
    #    unos pocos bytes, frente a un indice sobre toda la columna que con el tiempo
    #    apuntaria a millones de filas inactivas y no serviria para nada.
    # 2. Impone la invariante de que no puede haber DOS periodos activos a la vez. Es la
    #    razon por la que `PeriodRepository.find_active()` puede devolver un unico periodo
    #    sin ambiguedad: con dos filas activas, la consulta mas critica del sistema
    #    devolveria una u otra de forma arbitraria y el catalogo mostraria la oferta del
    #    semestre equivocado. Un UNIQUE parcial hace ese estado imposible; dejarlo en manos
    #    del endpoint de activacion seria confiar en que ningun otro camino de escritura se
    #    equivoque nunca.
    #
    # Las filas con `is_active = false` quedan fuera del indice, asi que puede haber tantos
    # periodos historicos como haga falta.
    op.create_index(
        "ix_enrollment_periods_active",
        "enrollment_periods",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )

    op.create_table(
        "professors",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_professors")),
        sa.UniqueConstraint("email", name=op.f("uq_professors_email")),
    )

    op.create_table(
        "course_offerings",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("enrollment_period_id", sa.UUID(), nullable=False),
        sa.Column("course_id", sa.UUID(), nullable=False),
        sa.Column("professor_id", sa.UUID(), nullable=True),
        sa.Column("group_number", sa.String(length=10), nullable=False),
        sa.Column("total_capacity", sa.Integer(), nullable=False),
        sa.Column("enrolled_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        # Bloqueo optimista: el UPDATE de inscripcion usa `WHERE version = :esperada`.
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
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
        # Red de seguridad final contra el sobrecupo.
        sa.CheckConstraint(
            "enrolled_count <= total_capacity",
            name=op.f("ck_course_offerings_capacity_not_exceeded"),
        ),
        sa.CheckConstraint(
            "enrolled_count >= 0", name=op.f("ck_course_offerings_enrolled_count_not_negative")
        ),
        sa.CheckConstraint("total_capacity > 0", name=op.f("ck_course_offerings_total_capacity")),
        # Sin `ondelete`: PostgreSQL aplica NO ACTION, de modo que borrar una materia con
        # grupos abiertos falla en vez de arrastrarlos.
        sa.ForeignKeyConstraint(
            ["course_id"], ["courses.id"], name=op.f("fk_course_offerings_course_id_courses")
        ),
        sa.ForeignKeyConstraint(
            ["enrollment_period_id"],
            ["enrollment_periods.id"],
            name=op.f("fk_course_offerings_enrollment_period_id_enrollment_periods"),
            ondelete="CASCADE",
        ),
        # SET NULL: dar de baja a un profesor no puede borrar los grupos que dictaba.
        sa.ForeignKeyConstraint(
            ["professor_id"],
            ["professors.id"],
            name=op.f("fk_course_offerings_professor_id_professors"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course_offerings")),
        sa.UniqueConstraint(
            "enrollment_period_id",
            "course_id",
            "group_number",
            name="uq_course_offerings_period_course_group",
        ),
    )
    op.create_index("ix_offerings_course", "course_offerings", ["course_id"], unique=False)
    op.create_index(
        "ix_offerings_period", "course_offerings", ["enrollment_period_id"], unique=False
    )

    op.create_table(
        "course_prerequisites",
        sa.Column("course_id", sa.UUID(), nullable=False),
        sa.Column("required_course_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "course_id <> required_course_id",
            name=op.f("ck_course_prerequisites_no_self_reference"),
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_course_prerequisites_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["required_course_id"],
            ["courses.id"],
            name=op.f("fk_course_prerequisites_required_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "course_id", "required_course_id", name=op.f("pk_course_prerequisites")
        ),
    )

    op.create_table(
        "program_courses",
        sa.Column("program_id", sa.UUID(), nullable=False),
        sa.Column("course_id", sa.UUID(), nullable=False),
        sa.Column("suggested_semester", sa.Integer(), nullable=False),
        sa.Column("is_mandatory", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint(
            "suggested_semester >= 1", name=op.f("ck_program_courses_suggested_semester")
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_program_courses_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["program_id"],
            ["programs.id"],
            name=op.f("fk_program_courses_program_id_programs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("program_id", "course_id", name=op.f("pk_program_courses")),
    )

    op.create_table(
        "schedule_blocks",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("course_offering_id", sa.UUID(), nullable=False),
        sa.Column("day_of_week", sa.SmallInteger(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("classroom", sa.String(length=50), nullable=True),
        sa.CheckConstraint(
            "day_of_week BETWEEN 1 AND 7", name=op.f("ck_schedule_blocks_day_of_week")
        ),
        sa.CheckConstraint(
            "end_time > start_time", name=op.f("ck_schedule_blocks_valid_time_range")
        ),
        sa.ForeignKeyConstraint(
            ["course_offering_id"],
            ["course_offerings.id"],
            name=op.f("fk_schedule_blocks_course_offering_id_course_offerings"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_schedule_blocks")),
    )
    op.create_index("ix_schedule_offering", "schedule_blocks", ["course_offering_id"], unique=False)

    # --- Auditoria temporal de la unica tabla nueva que muta ------------------
    # `set_updated_at()` ya existe: la creo la migracion 0003, que dejo anotado que las
    # migraciones de las Fases 2 y 3 solo tendrian que anadir su CREATE TRIGGER.
    op.execute(
        """
        CREATE TRIGGER trg_course_offerings_updated_at
            BEFORE UPDATE ON course_offerings
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """
    )


def downgrade() -> None:
    """Elimina el trigger y las siete tablas, de hija a padre."""
    op.execute("DROP TRIGGER IF EXISTS trg_course_offerings_updated_at ON course_offerings")

    op.drop_index("ix_schedule_offering", table_name="schedule_blocks")
    op.drop_table("schedule_blocks")
    op.drop_table("program_courses")
    op.drop_table("course_prerequisites")
    op.drop_index("ix_offerings_period", table_name="course_offerings")
    op.drop_index("ix_offerings_course", table_name="course_offerings")
    op.drop_table("course_offerings")
    op.drop_table("professors")
    op.drop_index(
        "ix_enrollment_periods_active",
        table_name="enrollment_periods",
        postgresql_where=sa.text("is_active = true"),
    )
    op.drop_table("enrollment_periods")
    op.drop_table("courses")
