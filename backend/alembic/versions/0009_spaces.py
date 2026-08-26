"""espacios: el aula deja de ser texto libre y pasa a ser una entidad

Crea `spaces` y sustituye `schedule_blocks.classroom` —una columna de texto libre— por una
clave foranea `space_id`.

POR QUE. Con el aula como texto, «A-201», «A201» y «Aula A-201» eran tres aulas distintas para
la base de datos y la misma para las personas. De ahi salen dos problemas que no se arreglan
validando la cadena: no habia forma fiable de responder «que hay en A-201 el martes a las 10», y
por tanto tampoco de impedir que dos grupos reservaran el mismo salon a la misma hora. Un texto
no puede estar ocupado; una fila si. Esta migracion es la mitad del arreglo; la otra es la
restriccion de exclusion de la iteracion 7.2, que necesita esta clave foranea para expresarse.

TRASLADO DE LOS DATOS. Cada texto DISTINTO no vacio de `classroom` se convierte en un espacio, y
despues cada franja se reengancha al suyo. El orden importa y es el unico posible: crear primero,
enganchar despues, borrar la columna al final. Si se borrara la columna antes de reenganchar, la
asignacion de aulas del semestre en curso se perderia entera y no habria de donde recuperarla.

Los espacios asi creados quedan con `space_type = 'CLASSROOM'` y **sin aforo**. Ninguno de los
dos datos esta en la cadena «A-201», y la alternativa —inventarlos— es peor que admitir que no
se saben: una capacidad inventada no la revisa nadie y se convierte en el numero contra el que
la 7.2 valida el aforo. `capacity` admite nulos justamente para poder decir «no se».

NORMALIZACION AL TRASLADAR. Los textos se comparan con `TRIM` y en mayusculas, para que
«a-201 » y «A-201» no produzcan dos filas distintas: seria arrastrar a la tabla nueva el mismo
problema que la tabla nueva viene a resolver. El codigo se guarda ya normalizado.

EL DOWNGRADE RECUPERA EL TEXTO a partir del codigo del espacio, asi que la asignacion de aulas
sobrevive a bajar. Lo que se pierde son los espacios que nadie tenia asignados y los datos que
la tabla anterior no sabia expresar —tipo, aforo, sede, bloque—, porque en una columna de texto
no caben.

Revision ID: 0009_spaces
Revises: 0008_requirement_reverse_index
Create Date: 2026-08-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009_spaces"
down_revision: str | None = "0008_requirement_reverse_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDICE_ESPACIO = "ix_schedule_space"


def upgrade() -> None:
    """Crea `spaces`, traslada los textos y cambia la columna por una clave foranea."""
    op.create_table(
        "spaces",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=True),
        sa.Column("space_type", sa.String(length=20), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("campus", sa.String(length=100), nullable=True),
        sa.Column("building", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "space_type IN ('CLASSROOM', 'LABORATORY', 'AUDITORIUM')",
            name=op.f("ck_spaces_space_type"),
        ),
        sa.CheckConstraint("capacity IS NULL OR capacity > 0", name=op.f("ck_spaces_capacity")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_spaces")),
        sa.UniqueConstraint("code", name=op.f("uq_spaces_code")),
    )

    op.add_column("schedule_blocks", sa.Column("space_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_schedule_blocks_space_id_spaces"),
        "schedule_blocks",
        "spaces",
        ["space_id"],
        ["id"],
        # SET NULL y no CASCADE: retirar un espacio del inventario no debe borrar la clase, debe
        # dejarla sin aula asignada, que es exactamente lo que ha ocurrido.
        ondelete="SET NULL",
    )

    # 1. Un espacio por cada texto distinto. `TRIM` + `UPPER` evita que «a-201 » y «A-201»
    #    creen dos filas: seria arrastrar a la tabla nueva el problema que viene a resolver.
    op.execute(
        sa.text(
            """
            INSERT INTO spaces (code, space_type)
            SELECT DISTINCT UPPER(TRIM(classroom)), 'CLASSROOM'
            FROM schedule_blocks
            WHERE classroom IS NOT NULL AND TRIM(classroom) <> ''
            """
        )
    )

    # 2. Reenganchar cada franja a su espacio, comparando igual que se creo.
    op.execute(
        sa.text(
            """
            UPDATE schedule_blocks AS sb
            SET space_id = s.id
            FROM spaces AS s
            WHERE s.code = UPPER(TRIM(sb.classroom))
            """
        )
    )

    # 3. Solo ahora se puede quitar la columna: hasta aqui era la unica fuente del dato.
    op.drop_column("schedule_blocks", "classroom")

    # El indice va al final, cuando la columna ya tiene sus valores: construirlo antes obligaria
    # a mantenerlo durante el UPDATE masivo del paso 2 para nada.
    #
    # PARCIAL sobre `space_id IS NOT NULL`: las franjas sin aula asignada no responden nada a la
    # pregunta «que hay reservado en este espacio», y con el tiempo serian la mayoria de un
    # indice que nunca las mira.
    op.create_index(
        INDICE_ESPACIO,
        "schedule_blocks",
        ["space_id", "day_of_week"],
        unique=False,
        postgresql_where=sa.text("space_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Devuelve la columna de texto con el codigo del espacio que tuviera cada franja."""
    op.drop_index(INDICE_ESPACIO, table_name="schedule_blocks")
    op.add_column(
        "schedule_blocks", sa.Column("classroom", sa.String(length=50), nullable=True)
    )

    op.execute(
        sa.text(
            """
            UPDATE schedule_blocks AS sb
            SET classroom = s.code
            FROM spaces AS s
            WHERE s.id = sb.space_id
            """
        )
    )

    op.drop_constraint(
        op.f("fk_schedule_blocks_space_id_spaces"), "schedule_blocks", type_="foreignkey"
    )
    op.drop_column("schedule_blocks", "space_id")
    op.drop_table("spaces")
