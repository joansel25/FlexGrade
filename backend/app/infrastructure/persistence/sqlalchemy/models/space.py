"""Modelo ORM de la tabla `spaces`: los espacios físicos donde se dicta clase.

Hasta la iteración 7.1 el aula era una columna de texto libre dentro de cada franja horaria,
`schedule_blocks.classroom`. Con eso, «A-201», «A201» y «Aula A-201» eran tres aulas distintas
para la base de datos y la misma para las personas, así que no había forma fiable de responder
«¿qué hay en A-201 el martes a las 10?» —y por tanto tampoco de impedir que dos grupos
reservaran el mismo salón a la misma hora—. Un texto no puede estar ocupado; una fila sí.

Esta tabla es la mitad del arreglo. La otra mitad es la restricción de exclusión de la
iteración 7.2, que necesita justamente esta clave foránea para expresarse.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Integer, String, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.sqlalchemy.models.base import Base


class SpaceModel(Base):
    """Un espacio físico de la institución.

    Attributes:
        id: identificador único, generado por PostgreSQL con `gen_random_uuid()`.
        code: código institucional (`A-201`). ÚNICO, y esa unicidad es la que convierte el
            código en clave natural: es lo que aparece en un horario impreso y lo que alguien
            escribe al asignar un aula, así que la API lo acepta en vez de exigir un UUID.
        name: nombre descriptivo, cuando lo tiene («Laboratorio de Redes»). La mayoría de las
            aulas no se llaman de ninguna manera, solo se numeran.
        space_type: `CLASSROOM`, `LABORATORY` o `AUDITORIUM`.
        capacity: aforo. **Nullable a propósito**, ver abajo.
        campus: sede en la que está.
        building: bloque o edificio dentro de la sede.
        created_at: instante de creación del registro.

    EL AFORO ADMITE NULOS, y no es dejadez. Los espacios que la migración `0009` creó a partir
    de los textos que ya existían en `schedule_blocks.classroom` no traían aforo de ninguna
    parte: en la cadena «A-201» no hay ningún número de sillas. Poner `NOT NULL` habría
    obligado a inventar una cifra para cada uno, y una capacidad inventada es peor que una
    ausente porque nadie vuelve a revisarla: se convierte en el dato contra el que la iteración
    7.2 valida el aforo. El `CHECK` exige que, cuando exista, sea positiva.

    EL TIPO SE VALIDA CON UN CHECK Y NO CON UN ENUM de PostgreSQL, igual que
    `enrollments.status` y `program_course_requirements.requirement_type`: añadir un valor a un
    ENUM obliga a un `ALTER TYPE` que no se puede revertir dentro de la misma migración,
    mientras que un CHECK se cambia con un `ALTER TABLE` corriente.
    """

    __tablename__ = "spaces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    space_type: Mapped[str] = mapped_column(String(20), nullable=False)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    campus: Mapped[str | None] = mapped_column(String(100), nullable=True)
    building: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    __table_args__ = (
        # Nombres cortos: la convención los expande a `ck_spaces_<nombre>`.
        CheckConstraint(
            "space_type IN ('CLASSROOM', 'LABORATORY', 'AUDITORIUM')",
            name="space_type",
        ),
        # `capacity IS NULL OR capacity > 0`: se admite no saber el aforo, nunca uno absurdo.
        CheckConstraint("capacity IS NULL OR capacity > 0", name="capacity"),
    )
