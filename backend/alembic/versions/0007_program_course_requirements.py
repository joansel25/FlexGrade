"""requisitos por plan: program_course_requirements sustituye a course_prerequisites

Mueve los requisitos academicos de "materia -> materia" a "materia dentro de un programa ->
materia", que es donde viven academicamente, y anade el correquisito como tipo propio.

POR QUE EL CAMBIO. `course_prerequisites` afirmaba que MAT102 exige MAT101 SIEMPRE, en toda la
institucion. Eso es falso en cuanto una materia entra en dos planes: la misma materia puede ser
obligatoria de segundo semestre con prerrequisito en Ingenieria y electiva libre en
Administracion. La tabla no tenia sitio para las dos verdades, asi que una de las dos tenia que
estar mal. Es el mismo motivo por el que `suggested_semester` e `is_mandatory` ya vivian en
`program_courses` y no en `courses`.

TRASLADO DE LOS DATOS. Cada fila antigua se replica en TODOS los programas donde las dos
materias —la que exige y la exigida— pertenecen al plan. Ese doble join no es un detalle de
implementacion, es la unica lectura conservadora posible: replicar donde solo aparece una de
las dos crearia un requisito que el estudiante no puede cursar nunca, y la clave foranea
compuesta hacia `program_courses` lo rechazaria de todas formas.

El traslado puede PERDER filas, y hay que saberlo: un prerrequisito entre dos materias que
ningun plan comparte no tiene programa al que pertenecer y desaparece. Con los datos del seed
eso no ocurre —cada cadena vive dentro de un solo programa—, pero en una base cargada a mano
conviene contar las filas antes de migrar.

LAS CLAVES FORANEAS COMPUESTAS son la mitad del valor de esta migracion. Apuntan a
`program_courses(program_id, course_id)` y no a `courses(id)`, de modo que PostgreSQL impide
declarar un requisito sobre una materia ajena al plan. Ese error —que el plan de Derecho exija
Programacion II— era posible antes y no se detectaba hasta que un estudiante se quedaba
bloqueado sin explicacion.

`requirement_type` es un VARCHAR con CHECK y no un ENUM de PostgreSQL, igual que
`enrollments.status`: anadir un valor a un ENUM obliga a un `ALTER TYPE` que no se puede
revertir dentro de la misma migracion, mientras que un CHECK se cambia con un `ALTER TABLE`
corriente. La garantia de conjunto cerrado es la misma.

El `downgrade` recupera `course_prerequisites` con los prerrequisitos, colapsando los
programas: si dos planes declaraban el mismo par, vuelve una sola fila. Los CORREQUISITOS SE
PIERDEN al bajar, porque la tabla antigua no tiene donde guardarlos. Esta dicho aqui para que
quien ejecute el downgrade sepa que no es una operacion sin coste.

Revision ID: 0007_program_requirements
Revises: 0006_enrollment_tables
Create Date: 2026-08-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007_program_requirements"
down_revision: str | None = "0006_enrollment_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea la tabla nueva, traslada los prerrequisitos y elimina la antigua."""
    op.create_table(
        "program_course_requirements",
        sa.Column("program_id", sa.UUID(), nullable=False),
        sa.Column("course_id", sa.UUID(), nullable=False),
        sa.Column("required_course_id", sa.UUID(), nullable=False),
        sa.Column("requirement_type", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "course_id <> required_course_id",
            name=op.f("ck_program_course_requirements_no_self_reference"),
        ),
        sa.CheckConstraint(
            "requirement_type IN ('PREREQUISITE', 'COREQUISITE')",
            name=op.f("ck_program_course_requirements_requirement_type"),
        ),
        sa.ForeignKeyConstraint(
            ["program_id", "course_id"],
            ["program_courses.program_id", "program_courses.course_id"],
            name="fk_pcr_course_in_plan",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["program_id", "required_course_id"],
            ["program_courses.program_id", "program_courses.course_id"],
            name="fk_pcr_required_course_in_plan",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "program_id",
            "course_id",
            "required_course_id",
            name=op.f("pk_program_course_requirements"),
        ),
    )

    # El traslado. `pc` situa la materia que exige dentro de un plan y `pr` comprueba que la
    # exigida esta en ESE MISMO plan; el join sobre `pr.program_id = pc.program_id` es lo que
    # impide fabricar requisitos entre carreras distintas.
    op.execute(
        sa.text(
            """
            INSERT INTO program_course_requirements
                (program_id, course_id, required_course_id, requirement_type)
            SELECT pc.program_id, cp.course_id, cp.required_course_id, 'PREREQUISITE'
            FROM course_prerequisites AS cp
            JOIN program_courses AS pc
                ON pc.course_id = cp.course_id
            JOIN program_courses AS pr
                ON pr.program_id = pc.program_id
               AND pr.course_id = cp.required_course_id
            """
        )
    )

    op.drop_table("course_prerequisites")


def downgrade() -> None:
    """Recrea `course_prerequisites` y devuelve los prerrequisitos, colapsando los programas.

    Los correquisitos no se recuperan: la tabla antigua no distingue el tipo, y devolverlos
    como prerrequisitos convertiria "cursala a la vez" en "aprueba la antes", que es una regla
    distinta y mas dura.
    """
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

    # `DISTINCT` obligatorio: el mismo par declarado en dos planes son dos filas aqui y una
    # sola alla, y sin el la insercion fallaria por clave duplicada.
    op.execute(
        sa.text(
            """
            INSERT INTO course_prerequisites (course_id, required_course_id)
            SELECT DISTINCT course_id, required_course_id
            FROM program_course_requirements
            WHERE requirement_type = 'PREREQUISITE'
            """
        )
    )

    op.drop_table("program_course_requirements")
