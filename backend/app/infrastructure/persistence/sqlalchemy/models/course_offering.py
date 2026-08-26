"""Modelo ORM de la tabla `course_offerings`: el grupo concreto que se dicta y se inscribe.

Corresponde al DDL de `docs/DATA_MODEL.md` sección 2. Es la tabla más sensible del sistema: sobre
ella se descuenta el cupo durante la ventana de matrícula, con miles de estudiantes compitiendo
por las mismas filas.

Dos columnas de esta tabla sostienen el requisito no funcional central, y ninguna sustituye a la
otra (`CLAUDE.md`, "El mecanismo que sostiene el requisito no funcional central"):

1. `version` — bloqueo optimista. El `UPDATE` de la inscripción lleva `WHERE version = :esperada`
   y reintenta un número limitado de veces si pierde la carrera contra otra transacción.
2. `CHECK (enrolled_count <= total_capacity)` — red de seguridad final. Si el bloqueo optimista
   fallara por un defecto de código, PostgreSQL rechaza la fila igualmente. Es la garantía de
   que el sobrecupo es imposible, no solo improbable.

La lógica que las usa llega en la Fase 3 (`EnrollStudentUseCase`). Aquí solo se declaran.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.sqlalchemy.models.base import Base


class CourseOfferingModel(Base):
    """Grupo de una materia en un período de matrícula concreto.

    Attributes:
        id: identificador único, generado por PostgreSQL con `gen_random_uuid()`.
        enrollment_period_id: ventana de matrícula a la que pertenece la oferta.
            `ON DELETE CASCADE`: los grupos de un período borrado no tienen sentido aparte.
        course_id: materia que se dicta. Sin `ON DELETE`: PostgreSQL aplica `NO ACTION`, de modo
            que borrar una materia con grupos abiertos falla en vez de arrastrarlos.
        professor_id: docente asignado. Es opcional: un grupo puede publicarse con el docente
            aún por asignar. `ON DELETE SET NULL` para que dar de baja a un profesor no borre
            los grupos que dictaba.
        group_number: número de grupo dentro de la materia (`01`, `02`). Es texto y no entero
            porque conserva el cero a la izquierda con el que la institución lo identifica.
        total_capacity: cupos totales del grupo. El `CHECK` impide un grupo de capacidad cero
            o negativa, que sería un grupo que nadie puede inscribir.
        enrolled_count: cupos ya ocupados. Es un contador desnormalizado a propósito: contar
            filas de `enrollments` en cada consulta de catálogo sería inviable bajo el pico de
            carga. La consistencia con `enrollments` la garantiza la transacción de inscripción.
        version: contador de bloqueo optimista. Se incrementa en cada modificación del cupo.
        created_at: instante de creación del registro.
        updated_at: instante de la última modificación, mantenido por el trigger
            `trg_course_offerings_updated_at`.
    """

    __tablename__ = "course_offerings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    enrollment_period_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("enrollment_periods.id", ondelete="CASCADE"),
        nullable=False,
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id"),
        nullable=False,
    )
    professor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("professors.id", ondelete="SET NULL"),
        nullable=True,
    )
    group_number: Mapped[str] = mapped_column(String(10), nullable=False)
    total_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    enrolled_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        # Redundante para los datos —`id` ya es clave primaria— y OBLIGATORIO para PostgreSQL:
        # `schedule_blocks` referencia estas dos columnas con una clave foránea compuesta, y
        # referenciar dos columnas exige un índice único sobre ellas. Es lo que permite atar la
        # copia desnormalizada del período que necesita la restricción de doble reserva.
        UniqueConstraint("id", "enrollment_period_id", name="id_enrollment_period_id"),
        # Nombres cortos: la convención los expande a `ck_course_offerings_<nombre>`.
        CheckConstraint("total_capacity > 0", name="total_capacity"),
        CheckConstraint("enrolled_count >= 0", name="enrolled_count_not_negative"),
        # La red de seguridad contra el sobrecupo. No es redundante con el bloqueo optimista:
        # es la garantía que sigue en pie aunque el bloqueo falle.
        CheckConstraint("enrolled_count <= total_capacity", name="capacity_not_exceeded"),
        # Un mismo grupo de una materia no puede repetirse dentro del mismo período.
        UniqueConstraint(
            "enrollment_period_id",
            "course_id",
            "group_number",
            name="uq_course_offerings_period_course_group",
        ),
        # Índices con nombre explícito, según el DDL de `docs/DATA_MODEL.md`. El de la
        # restricción UNIQUE de arriba también empieza por `enrollment_period_id`, pero ordena
        # por tres columnas y es bastante más ancho; `ix_offerings_period` resuelve el listado
        # de grupos del período activo —la consulta más frecuente del catálogo— con mucho menos
        # trabajo de lectura.
        Index("ix_offerings_period", "enrollment_period_id"),
        Index("ix_offerings_course", "course_id"),
    )
