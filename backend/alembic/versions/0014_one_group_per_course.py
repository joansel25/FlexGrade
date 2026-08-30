"""Una materia, un grupo por período: la segunda defensa contra la matrícula doble.

El sistema permitía inscribirse en DOS grupos de la misma materia a la vez, y lo permitía de
punta a punta: el caso de uso comprobaba el duplicado por GRUPO
(`find_by_student_and_offering`) y la restricción de la base era
`UNIQUE (student_id, course_offering_id, enrollment_period_id)`, también por grupo. Nadie
miraba la materia.

**Lo que estaba en juego no era el horario duplicado.** `academic_history` es único por
`(student_id, course_id, academic_period)`: dos grupos de la misma materia producen dos filas
idénticas al consolidar, y el cierre del semestre —la única operación irreversible del
sistema— falla entero. Se podía crear un estado del que no había salida.

**Por qué pasó desapercibido:** dos grupos de la misma materia suelen cruzarse en el horario, y
el detector de choques los rechazaba por el motivo equivocado. Cuando no se cruzaban —el grupo
01 el lunes y el 02 el martes— no los rechazaba nadie.

**Por qué `course_id` se copia en `enrollments`.** Un índice único solo mira columnas de su
tabla, y la materia vivía únicamente en `course_offerings`. Es la misma copia deliberada que
`schedule_blocks.enrollment_period_id`, y se protege igual: con una clave foránea COMPUESTA
contra `course_offerings (id, course_id)`, que impide que la copia mienta.

**El índice es PARCIAL sobre las activas.** Cancelar un grupo y tomar otro de la misma materia
es una operación legítima y frecuente; sin el `WHERE`, la fila cancelada bloquearía para siempre
volver a inscribir esa materia.

Las filas que ya violaban la regla se CANCELAN, no se borran: cancelar es como este sistema
deshace una inscripción y deja rastro de que ocurrió. Se conserva la más antigua —la que la
persona eligió primero— y se devuelve el cupo al grupo, que de otro modo quedaría descontado
para nadie.

Revision ID: 0014_one_group_per_course
Revises: 0013_period_consolidation
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_one_group_per_course"
down_revision = "0013_period_consolidation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. La copia de la materia. Nullable de entrada porque todavía hay que rellenarla.
    op.add_column(
        "enrollments",
        sa.Column("course_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )

    op.execute(
        """
        UPDATE enrollments e
           SET course_id = co.course_id
          FROM course_offerings co
         WHERE co.id = e.course_offering_id
        """
    )

    op.alter_column("enrollments", "course_id", nullable=False)

    # 2. Las inscripciones que ya violaban la regla. Se cancela la MÁS NUEVA de cada grupo de
    #    duplicados y se conserva la primera, que es la que la persona eligió antes de que el
    #    sistema le dejara equivocarse.
    op.execute(
        """
        WITH duplicadas AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY student_id, course_id, enrollment_period_id
                       ORDER BY enrolled_at
                   ) AS puesto,
                   course_offering_id
              FROM enrollments
             WHERE status = 'ENROLLED'
        ),
        canceladas AS (
            UPDATE enrollments e
               SET status = 'CANCELLED',
                   cancelled_at = now()
              FROM duplicadas d
             WHERE e.id = d.id AND d.puesto > 1
            RETURNING d.course_offering_id
        )
        UPDATE course_offerings co
           SET enrolled_count = co.enrolled_count - devueltos.cuantos
          FROM (
                SELECT course_offering_id, COUNT(*) AS cuantos
                  FROM canceladas
                 GROUP BY course_offering_id
               ) AS devueltos
         WHERE co.id = devueltos.course_offering_id
        """
    )

    # 3. La clave foránea compuesta: es lo que impide que `enrollments.course_id` diga una
    #    materia distinta de la del grupo al que apunta.
    op.create_unique_constraint(
        "uq_course_offerings_id_course", "course_offerings", ["id", "course_id"]
    )
    op.create_foreign_key(
        "fk_enrollments_offering_course",
        "enrollments",
        "course_offerings",
        ["course_offering_id", "course_id"],
        ["id", "course_id"],
    )

    # 4. La garantía. Parcial sobre las activas: ver la cabecera.
    op.create_index(
        "uq_enrollments_active_student_course_period",
        "enrollments",
        ["student_id", "course_id", "enrollment_period_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ENROLLED'"),
    )


def downgrade() -> None:
    # Las inscripciones canceladas en el `upgrade` NO se restauran: no hay forma de distinguir
    # las que canceló esta migración de las que canceló una persona, y revivir las segundas
    # devolvería a alguien a una materia que abandonó.
    op.drop_index("uq_enrollments_active_student_course_period", table_name="enrollments")
    op.drop_constraint("fk_enrollments_offering_course", "enrollments", type_="foreignkey")
    op.drop_constraint("uq_course_offerings_id_course", "course_offerings", type_="unique")
    op.drop_column("enrollments", "course_id")
