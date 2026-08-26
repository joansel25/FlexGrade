"""El período se puede consolidar, y una vez consolidado no se toca.

Es la pieza que cierra el ciclo académico. Hasta aquí, `academic_history` solo la escribía el
seed: en producción habría quedado vacía para siempre, `find_approved_course_ids` habría
devuelto vacío y NADIE habría cumplido ningún prerrequisito a partir del segundo semestre. El
sistema funcionaba un solo semestre de su vida.

`consolidated_at` es una MARCA DE TIEMPO y no un booleano. Un `boolean` diría que ocurrió;
la fecha dice además cuándo, que es lo primero que se pregunta cuando alguien reclama una nota
—«¿se cerró antes o después de que la corrigieran?»— y no se puede reconstruir después.

NULLABLE porque «todavía no consolidado» es el estado normal de un período durante todo el
semestre. Sin valor por defecto: no hay ninguno que signifique «aún no» mejor que la ausencia.

Revision ID: 0013_period_consolidation
Revises: 0012_enrollment_grades
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_period_consolidation"
down_revision = "0012_enrollment_grades"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "enrollment_periods",
        sa.Column("consolidated_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    # Un período consolidado no puede estar activo. Consolidar cierra el semestre: dejarlo
    # abierto permitiría que alguien se matriculara en un período cuyo expediente ya se escribió,
    # y esa inscripción no llegaría nunca al historial porque la consolidación ya pasó.
    #
    # Se comprueba con un CHECK y no solo en el caso de uso porque el estado prohibido es
    # invisible: nada falla, simplemente unas matrículas se pierden en silencio meses después.
    op.create_check_constraint(
        "consolidated_is_closed",
        "enrollment_periods",
        "consolidated_at IS NULL OR is_active = false",
    )


def downgrade() -> None:
    op.drop_constraint("consolidated_is_closed", "enrollment_periods", type_="check")
    op.drop_column("enrollment_periods", "consolidated_at")
