"""Entidad CourseOffering: el grupo concreto que se dicta y se inscribe."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from app.domain.entities.professor import Professor
from app.domain.value_objects.schedule_block import ScheduleBlock


@dataclass
class CourseOffering:
    """Grupo de una materia en un período de matrícula concreto.

    Es la entidad sobre la que se descuenta el cupo, y por tanto el centro del requisito no
    funcional del sistema.

    Lleva dentro su docente y sus franjas de horario en vez de solo los identificadores. Es
    una decisión deliberada: el catálogo siempre los muestra juntos, y resolverlos aparte
    obligaría a una consulta por grupo (el problema N+1) justo en el endpoint que más se
    consulta durante el pico de matrícula. El repositorio los trae en una sola consulta y
    entrega el grupo ya completo.

    Attributes:
        id: identificador único del grupo.
        enrollment_period_id: ventana de matrícula a la que pertenece.
        course_id: materia que se dicta.
        group_number: número de grupo dentro de la materia (`01`, `02`).
        total_capacity: cupos totales.
        enrolled_count: cupos ya ocupados.
        version: contador del bloqueo optimista. Lo usará el descuento de cupo en la Fase 3;
            aquí se transporta para que el caso de uso pueda comparar la versión que leyó
            contra la que hay en la base al escribir.
        professor: docente asignado, o `None` si aún no se ha asignado.
        schedule: franjas semanales en las que se dicta el grupo.
    """

    id: UUID
    enrollment_period_id: UUID
    course_id: UUID
    group_number: str
    total_capacity: int
    enrolled_count: int
    version: int
    professor: Professor | None = None
    schedule: tuple[ScheduleBlock, ...] = field(default_factory=tuple)

    def available_slots(self) -> int:
        """Cupos que quedan libres.

        Nunca devuelve un número negativo: el `CHECK` de la base de datos garantiza que
        `enrolled_count` jamás supere la capacidad, pero el `max` deja la entidad correcta
        por sí sola, sin depender de una garantía que vive fuera del dominio.

        Returns:
            Los cupos disponibles en este momento.
        """
        return max(0, self.total_capacity - self.enrolled_count)

    def is_full(self) -> bool:
        """Indica si el grupo ya no admite más inscripciones."""
        return self.available_slots() == 0
