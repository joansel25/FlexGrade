"""doble reserva imposible: restriccion de exclusion GiST sobre los espacios

Es la red final de la Fase 7, y el paralelo exacto del `CHECK (enrolled_count <= total_capacity)`
que impide el sobrecupo: la validacion del caso de uso existe para dar un mensaje util, y ESTA
restriccion existe para que el estado imposible no pueda escribirse aunque el codigo falle. Sin
ella, dos peticiones simultaneas pueden comprobar a la vez que un aula esta libre y reservarla
las dos; ninguna comprobacion en la aplicacion cierra esa carrera.

QUE IMPIDE. Dos franjas que se solapen en el MISMO espacio, el MISMO dia y el MISMO periodo de
matricula.

POR QUE HACE FALTA `enrollment_period_id` EN `schedule_blocks`. Una restriccion de exclusion
solo puede mirar columnas de SU tabla, y el periodo vive en `course_offerings`. Sin esa columna,
la restriccion prohibiria reutilizar un aula el semestre siguiente a la misma hora, que es lo
normal y no un conflicto. La columna se desnormaliza, pero NO queda a merced del codigo: la
clave foranea es COMPUESTA sobre `(course_offering_id, enrollment_period_id)` contra
`course_offerings(id, enrollment_period_id)`, asi que PostgreSQL impide que una franja declare
un periodo distinto al de su grupo. Es el mismo recurso que usa `program_course_requirements`
para impedir requisitos fuera del plan.

POR QUE `tsrange` Y NO UN TIPO `timerange`. PostgreSQL no trae un rango sobre `time`, y crear un
tipo propio complica la migracion sin necesidad: un tipo no se puede borrar mientras algo lo use
y su `downgrade` es mas fragil. Anclando las horas a una fecha fija —`DATE '2000-01-01' +
start_time`— se obtiene un `tsrange` con tipos nativos. La fecha da igual mientras sea la misma
para todas las filas: lo unico que se compara son horas del mismo dia, y `day_of_week` ya
separa los dias.

`[)` en el rango, no `[]`: una clase que termina a las 10:00 y otra que empieza a las 10:00 son
consecutivas, no un choque. Es la misma regla que aplica `ScheduleBlock.overlaps` con su
comparacion estricta, y ponerla `[]` marcaria como conflicto un horario perfectamente valido.

`WHERE (space_id IS NOT NULL)`: una franja sin aula asignada no ocupa nada. Sin este filtro,
todas las clases sin espacio del mismo dia y hora chocarian entre si, y publicar un horario
antes de repartir aulas —que es el orden normal— seria imposible.

`btree_gist` es imprescindible: GiST no sabe comparar por igualdad un `uuid` ni un `smallint`
por su cuenta, y `space_id WITH =` y `day_of_week WITH =` lo necesitan.

Revision ID: 0010_no_double_booking
Revises: 0009_spaces
Create Date: 2026-08-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_no_double_booking"
down_revision: str | None = "0009_spaces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RESTRICCION = "ex_schedule_blocks_no_double_booking"
FK_PERIODO = "fk_schedule_blocks_offering_period"
UQ_OFERTA = "uq_course_offerings_id_period"

#: El rango horario de una franja, anclado a una fecha fija. Se repite en la restriccion y en
#: nada mas, pero se nombra para que el `downgrade` y el `upgrade` no puedan divergir.
_RANGO = "tsrange(DATE '2000-01-01' + start_time, DATE '2000-01-01' + end_time, '[)')"


def upgrade() -> None:
    """Desnormaliza el periodo en las franjas y prohibe la doble reserva."""
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS btree_gist"))

    # 1. La columna del periodo. Nace opcional para poder rellenarla; se cierra despues.
    op.add_column(
        "schedule_blocks", sa.Column("enrollment_period_id", sa.UUID(), nullable=True)
    )
    op.execute(
        sa.text(
            """
            UPDATE schedule_blocks AS sb
            SET enrollment_period_id = co.enrollment_period_id
            FROM course_offerings AS co
            WHERE co.id = sb.course_offering_id
            """
        )
    )
    op.alter_column("schedule_blocks", "enrollment_period_id", nullable=False)

    # 2. La clave foranea compuesta, que es lo que impide que la copia mienta. Referenciar dos
    #    columnas exige que exista un indice unico sobre ellas en la tabla destino; `id` ya es
    #    clave primaria, asi que este UNIQUE es redundante para los datos y obligatorio para
    #    PostgreSQL.
    op.create_unique_constraint(
        UQ_OFERTA, "course_offerings", ["id", "enrollment_period_id"]
    )
    op.create_foreign_key(
        FK_PERIODO,
        "schedule_blocks",
        "course_offerings",
        ["course_offering_id", "enrollment_period_id"],
        ["id", "enrollment_period_id"],
        ondelete="CASCADE",
    )

    # 3. Liberar las dobles reservas que YA existen.
    #
    #    No es un caso hipotetico: es la norma. Mientras el aula fue texto libre nada impidio
    #    reservar el mismo salon dos veces, asi que cualquier base real llega aqui con
    #    conflictos y `ADD CONSTRAINT` los rechaza en bloque. Una migracion que solo funciona
    #    sobre datos limpios no sirve para el unico caso en que hace falta.
    #
    #    Se resuelve DEJANDO SIN AULA a la franja que llego despues, nunca borrandola: la clase
    #    existe y su horario es correcto, lo que esta mal es donde se dijo que era. «Sin aula
    #    asignada» ya es un estado que el sistema entiende —el horario se publica antes de
    #    repartir espacios— y deja el problema a la vista de quien tiene que reasignarla, en vez
    #    de esconderlo.
    #
    #    `otro.id < sb.id` da un desempate determinista: de cada grupo de franjas en conflicto
    #    sobrevive una sola. Puede liberar alguna de mas en cadenas largas (A choca con B, B con
    #    C, pero A no con C), y se acepta: pasarse de conservador deja aulas por reasignar,
    #    quedarse corto deja la restriccion sin poder crearse.
    liberadas = op.get_bind().execute(
        sa.text(
            """
            UPDATE schedule_blocks AS sb
            SET space_id = NULL
            WHERE sb.space_id IS NOT NULL
              AND EXISTS (
                  SELECT 1
                  FROM schedule_blocks AS otro
                  WHERE otro.space_id = sb.space_id
                    AND otro.enrollment_period_id = sb.enrollment_period_id
                    AND otro.day_of_week = sb.day_of_week
                    AND otro.id < sb.id
                    AND otro.start_time < sb.end_time
                    AND sb.start_time < otro.end_time
              )
            """
        )
    ).rowcount

    if liberadas:
        print(
            f"[0010] {liberadas} franja(s) estaban doblemente reservadas y quedaron SIN AULA. "
            "Hay que reasignarlas: la clase sigue en pie, el espacio no."
        )

    # 4. La red final.
    op.execute(
        sa.text(
            f"""
            ALTER TABLE schedule_blocks
            ADD CONSTRAINT {RESTRICCION}
            EXCLUDE USING gist (
                space_id WITH =,
                enrollment_period_id WITH =,
                day_of_week WITH =,
                {_RANGO} WITH &&
            )
            WHERE (space_id IS NOT NULL)
            """
        )
    )


def downgrade() -> None:
    """Retira la restriccion y la columna desnormalizada.

    Al bajar, la doble reserva vuelve a ser posible: la validacion del caso de uso sigue en pie,
    pero deja de haber nada que impida la carrera entre dos peticiones simultaneas.
    """
    op.execute(sa.text(f"ALTER TABLE schedule_blocks DROP CONSTRAINT IF EXISTS {RESTRICCION}"))
    op.drop_constraint(FK_PERIODO, "schedule_blocks", type_="foreignkey")
    op.drop_constraint(UQ_OFERTA, "course_offerings", type_="unique")
    op.drop_column("schedule_blocks", "enrollment_period_id")
    # `btree_gist` no se elimina: pudo instalarla otra cosa, y una extension compartida no la
    # retira quien no la puso.
