"""Entidad CourseOffering: el grupo concreto que se dicta y se inscribe."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from app.domain.entities.professor import Professor
from app.domain.exceptions.enrollment import CapacityExceededError
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

    def can_accept_enrollment(self) -> bool:
        """Indica si queda al menos un cupo libre.

        Es una consulta sin efectos: responde sin cambiar nada. Sirve para mostrar el estado
        del grupo en el catálogo. **No** es la comprobación que protege contra el sobrecupo:
        entre preguntar y descontar puede colarse otra transacción, así que quien inscribe
        debe llamar directamente a `reserve_slot()`, que comprueba y descuenta sin dejar
        hueco entre ambas cosas.
        """
        return not self.is_full()

    def reserve_slot(self) -> None:
        """Ocupa un cupo del grupo.

        Aquí vive la invariante de capacidad, y vive en la entidad a propósito
        (`ARCHITECTURE.md` sección 4): la regla no está dispersa entre el caso de uso, el
        repositorio y el SQL, sino en un único método que se puede probar en milisegundos sin
        base de datos.

        Este método por sí solo **no** basta contra la concurrencia, y es importante no
        confundirse: opera sobre una copia en memoria del grupo. Dos peticiones simultáneas
        pueden leer `enrolled_count = 39` y ambas pasar esta comprobación. Lo que resuelve la
        carrera es el `UPDATE ... WHERE version = :esperada` que ejecuta el repositorio con el
        resultado de este método, más el `CHECK` de PostgreSQL como red final.

        La defensa en profundidad es deliberada: esta comprobación descarta de inmediato el
        caso obvio —el grupo ya estaba lleno cuando se leyó— sin gastar una escritura, y deja
        al bloqueo optimista solo la carrera real por el último cupo.

        Raises:
            CapacityExceededError: si el grupo ya está lleno.
        """
        if self.is_full():
            raise CapacityExceededError(self.id, self.total_capacity, self.enrolled_count)

        self.enrolled_count += 1
        # La versión se incrementa aquí para que el repositorio persista el par
        # (enrolled_count, version) coherente. El `UPDATE` comparará contra la versión que
        # tenía la entidad al leerse, que es `self.version - 1`.
        self.version += 1

    def release_slot(self) -> None:
        """Libera un cupo del grupo, al cancelarse una inscripción.

        Nunca deja `enrolled_count` por debajo de cero. La guarda no es teórica: si una
        cancelación se procesara dos veces, el contador quedaría por debajo de la ocupación
        real y aparecerían cupos fantasma que dos personas podrían tomar. La primera línea de
        defensa es `Enrollment.cancel()`, que rechaza cancelar lo ya cancelado; esta es la
        segunda.
        """
        if self.enrolled_count > 0:
            self.enrolled_count -= 1

        self.version += 1
