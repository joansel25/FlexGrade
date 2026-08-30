"""Entidad Enrollment: la inscripción de un estudiante en un grupo."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.domain.exceptions.enrollment import (
    CannotGradeCancelledEnrollmentError,
    EnrollmentAlreadyCancelledError,
)
from app.domain.value_objects.enrollment_status import EnrollmentStatus
from app.domain.value_objects.grade import Grade


@dataclass
class Enrollment:
    """Inscripción de un estudiante en un grupo dentro de un período.

    Attributes:
        id: identificador único de la inscripción.
        student_id: estudiante inscrito.
        course_offering_id: grupo en el que se inscribió.
        course_id: materia de ese grupo. Se guarda junto al grupo, y no se deduce de él, porque
            la regla «una materia, un grupo por período» se comprueba sobre la MATERIA y la
            base necesita el dato en la propia fila para poder garantizarla (migración `0014`).
        enrollment_period_id: ventana de matrícula en la que ocurrió.
        status: estado actual.
        enrolled_at: instante de la inscripción.
        cancelled_at: instante de la cancelación, si la hubo.
        final_grade: nota final, o `None` mientras no se haya calificado. Es un BORRADOR: vive
            aquí y no en `academic_history` para que corregirla siga siendo posible hasta que
            la 9.3 consolide el período.
        graded_at: instante de la última calificación. Va con la nota o no va: una nota sin
            fecha no dice cuándo se puso, y una fecha sin nota no significa nada.
    """

    id: UUID
    student_id: UUID
    course_offering_id: UUID
    course_id: UUID
    enrollment_period_id: UUID
    status: EnrollmentStatus = EnrollmentStatus.ENROLLED
    enrolled_at: datetime | None = field(default=None)
    cancelled_at: datetime | None = field(default=None)
    final_grade: Grade | None = field(default=None)
    graded_at: datetime | None = field(default=None)

    def grade(self, nota: Grade, *, now: datetime) -> None:
        """Registra o corrige la nota final.

        Args:
            nota: la calificación, ya validada en su rango por el value object.
            now: instante que queda registrado.

        Raises:
            CannotGradeCancelledEnrollmentError: si la inscripción está cancelada. Una materia
                que se dio de baja no se cursó, así que no hay nada que calificar, y una nota
                sobre ella viajaría al historial en la consolidación como si se hubiera cursado.
        """
        if self.status is not EnrollmentStatus.ENROLLED:
            raise CannotGradeCancelledEnrollmentError(self.id)

        self.final_grade = nota
        self.graded_at = now

    def esta_calificada(self) -> bool:
        """Indica si ya tiene nota."""
        return self.final_grade is not None

    @classmethod
    def create(
        cls,
        *,
        student_id: UUID,
        course_offering_id: UUID,
        course_id: UUID,
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
            course_id: materia de ese grupo.
            enrollment_period_id: ventana de matrícula vigente.

        Returns:
            La inscripción lista para persistirse.
        """
        return cls(
            id=uuid4(),
            student_id=student_id,
            course_offering_id=course_offering_id,
            course_id=course_id,
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
