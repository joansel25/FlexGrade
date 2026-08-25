"""indice inverso de requisitos, para la regla de cancelacion

La iteracion 6.2 dejo `program_course_requirements` con una sola forma de consultarse: "que
exige esta materia", que filtra por `(program_id, course_id)` y la resuelve el indice de la
clave primaria. Su modelo lo decia explicitamente: no hacia falta ningun indice mas.

Esta iteracion anade la pregunta CONTRARIA —"que materias exigen a esta como correquisito"—,
que es la que sostiene la regla de cancelacion: antes de dejar que alguien cancele `MAT101` hay
que saber si sigue inscrito en `FIS101`, que exige cursarla a la vez. Esa consulta filtra por
`(program_id, required_course_id)`, y esas dos columnas NO son un prefijo de la clave primaria
`(program_id, course_id, required_course_id)`: el indice de la PK no puede resolverla.

Sin este indice PostgreSQL recorreria la tabla entera en cada cancelacion. Hoy la tabla tiene
nueve filas y no se notaria en absoluto; con los planes de estudio completos de una institucion
son miles, y el recorrido caeria dentro de la transaccion de cancelacion, que libera un cupo y
compite con las inscripciones en plena ventana de matricula. Es el momento exacto en el que no
conviene tener un `Seq Scan`.

Se indexa `(program_id, required_course_id)` y no solo `required_course_id`: toda consulta del
sistema acota primero por programa, y con la columna del programa delante el indice sirve
tambien para responder por programa solo, mientras que al reves no.

No lleva `requirement_type` aunque la consulta lo filtre. Anadirlo haria el indice mas ancho
para descartar unas pocas filas por materia —las que son prerrequisito en vez de correquisito—,
que PostgreSQL descarta igual de barato al leer la fila. El indice esta para evitar el
recorrido, no para responder la consulta entera.

Revision ID: 0008_requirement_reverse_index
Revises: 0007_program_requirements
Create Date: 2026-08-25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008_requirement_reverse_index"
down_revision: str | None = "0007_program_requirements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Nombre corto y explicito. La convencion de `base.py` compondria
# `ix_program_course_requirements_program_id_required_course_id`, que pasa de los 63 caracteres
# que admite un identificador de PostgreSQL: la base lo truncaria y el nombre dejaria de
# coincidir con el que espera esta migracion.
INDICE = "ix_program_course_requirements_required"


def upgrade() -> None:
    """Crea el indice que resuelve la consulta inversa de correquisitos."""
    op.create_index(
        INDICE,
        "program_course_requirements",
        ["program_id", "required_course_id"],
        unique=False,
    )


def downgrade() -> None:
    """Elimina el indice. La consulta sigue funcionando, solo que recorriendo la tabla."""
    op.drop_index(INDICE, table_name="program_course_requirements")
