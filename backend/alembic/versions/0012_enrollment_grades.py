"""La nota vive en la inscripción mientras el período está abierto.

LA NOTA NO SE ESCRIBE DIRECTAMENTE EN `academic_history`, y esa es la decisión que gobierna la
Fase 9. El historial es un registro consolidado: lo que hay ahí decide prerrequisitos y aparece
en el expediente. Escribir cada tecleo del docente directamente allí haría irreversible una
corrección tan normal como equivocarse de fila.

Así que la nota nace como BORRADOR en `enrollments.final_grade`, corregible mientras el semestre
está abierto, y la 9.3 la consolida en `academic_history` en una sola operación transaccional.

`NUMERIC(3,2)` y no `REAL`: `0.1 + 0.2` no es `0.3` en coma flotante, y una nota que cae en la
frontera de aprobación decidiría el semestre de alguien según un error de redondeo binario.

El `CHECK` del rango es la red final, con la misma filosofía de dos defensas que sostiene el
control de cupos: `Grade` da el mensaje útil y la base impide que entre por cualquier otro
camino —el seed, una migración, un caso de uso futuro— una nota de otra escala.

Revision ID: 0012_enrollment_grades
Revises: 0011_professor_accounts
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_enrollment_grades"
down_revision = "0011_professor_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NULLABLE, y no es un hueco que rellenar: «todavía sin calificar» es el estado normal de
    # una inscripción durante casi todo el semestre. Un cero por defecto sería una nota, y una
    # reprobatoria: el peor valor posible para significar «no lo sé».
    op.add_column(
        "enrollments", sa.Column("final_grade", sa.Numeric(3, 2), nullable=True)
    )
    op.add_column(
        "enrollments",
        sa.Column("graded_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "final_grade_range",
        "enrollments",
        "final_grade IS NULL OR (final_grade >= 0 AND final_grade <= 5)",
    )
    # La nota y su instante van juntas o no van. Sin esto, un `UPDATE` a mano podría dejar una
    # nota sin fecha —y la 9.3 no sabría si se calificó— o una fecha sin nota, que no significa
    # nada.
    op.create_check_constraint(
        "graded_at_with_grade",
        "enrollments",
        "(final_grade IS NULL) = (graded_at IS NULL)",
    )
    # Índice PARCIAL sobre lo que falta por calificar. Es la consulta que la 9.3 ejecuta antes
    # de consolidar —«¿queda alguna inscripción sin nota?»— y la que la pantalla del docente usa
    # para decir cuántas quedan. Parcial porque al final del semestre casi todas están
    # calificadas, y un índice completo almacenaría miles de filas para responder sobre unas
    # pocas.
    op.create_index(
        "ix_enrollments_pending_grade",
        "enrollments",
        ["enrollment_period_id"],
        postgresql_where=sa.text("final_grade IS NULL AND status = 'ENROLLED'"),
    )


def downgrade() -> None:
    op.drop_index("ix_enrollments_pending_grade", table_name="enrollments")
    op.drop_constraint("graded_at_with_grade", "enrollments", type_="check")
    op.drop_constraint("final_grade_range", "enrollments", type_="check")
    op.drop_column("enrollments", "graded_at")
    op.drop_column("enrollments", "final_grade")
