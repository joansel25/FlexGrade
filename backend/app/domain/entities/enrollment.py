"""Entidad Enrollment: la inscripción de un estudiante en un grupo."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.domain.exceptions.enrollment import EnrollmentAlreadyCancelledError
from app.domain.value_objects.enrollment_status import EnrollmentStatus


@dataclass
class Enrollment:
    """Inscripción de un estudiante en un grupo dentro de un período.

    Attributes:
        id: identificador único de la inscripción.
        student_id: estudiante inscrito.
        course_offering_id: grupo en el que se inscribió.
        enrollment_period_id: ventana de matrícula en la que ocurrió.
        status: estado actual.
        enrolled_at: instante de la inscripción.
        cancelled_at: instante de la cancelación, si la hubo.
    """

    id: UUID
    student_id: UUID
    course_offering_id: UUID
    enrollment_period_id: UUID
    status: EnrollmentStatus = EnrollmentStatus.ENROLLED
    enrolled_at: datetime | None = field(default=None)
    cancelled_at: datetime | None = field(default=None)

    @classmethod
    def create(
        cls,
        *,
        student_id: UUID,
        course_offering_id: UUID,
        enrollment_period_id: UUID,
    ) -> Enrollment:
        """Crea una inscripción nueva, ya activa.

        El identificador se genera aquí y no en la base de datos aunque la columna tenga
        `DEFAULT gen_random_uuid()`. La razón es concreta: el caso de uso necesita conocerlo
        para devolverlo en la respuesta, y esperar a que PostgreSQL lo asigne obligaría a un
        `flush` intermedio dentro de la transacción crítica de la inscripción.

        `enrolled_at` se deja en `None` a propósito: lo pone la base de datos con su
        `DEFAULT NOW()`, que es la única fuente horaria fiable cuando varias instancias de la
        aplicación pueden tener relojes ligeramente distintos.

        Args:
            student_id: estudiante que se inscribe.
            course_offering_id: grupo elegido.
            enrollment_period_id: ventana de matrícula vigente.

        Returns:
            La inscripción lista para persistirse.
        """
        return cls(
            id=uuid4(),
            student_id=student_id,
            course_offering_id=course_offering_id,
            enrollment_period_id=enrollment_period_id,
            status=EnrollmentStatus.ENROLLED,
        )

    def is_active(self) -> bool:
        """Indica si la inscripción está vigente.

        Solo `ENROLLED` cuenta como activa: una inscripción cancelada no ocupa cupo, no entra
        en el horario del estudiante y no bloquea una inscripción nueva en el mismo grupo.
        """
        return self.status is EnrollmentStatus.ENROLLED

    def cancel(self, now: datetime) -> None:
        """Cancela la inscripción.

        Args:
            now: instante de la cancelación. Se recibe por parámetro y no se lee el reloj aquí
                dentro para que la regla sea comprobable sin depender de la hora real.

        Raises:
            EnrollmentAlreadyCancelledError: si ya estaba cancelada. Es una guarda con
                consecuencias reales: cancelar dos veces liberaría el cupo dos veces, y el
                segundo `release_slot()` dejaría `enrolled_count` por debajo de la ocupación
                real. Ese hueco fantasma lo podrían tomar dos personas.
        """
        if not self.is_active():
            raise EnrollmentAlreadyCancelledError(self.id)

        self.status = EnrollmentStatus.CANCELLED
        self.cancelled_at = now

    def reactivate(self) -> None:
        """Vuelve a activar una inscripción cancelada.

        Existe porque la restricción `UNIQUE (student_id, course_offering_id,
        enrollment_period_id)` impide crear una fila nueva cuando alguien cancela y se
        reinscribe en el mismo grupo. En vez de duplicar el registro —o de borrarlo, perdiendo
        el rastro de que hubo una cancelación— se reactiva el existente.
        """
        self.status = EnrollmentStatus.ENROLLED
        self.cancelled_at = None
