"""Puerto de persistencia del agregado Enrollment.

Segregado en lector y escritor (`ARCHITECTURE.md` sección 5, principio I). No es purismo: los
reportes de la Fase 4 y la consulta del horario solo leen, y hacerles depender de un contrato
que incluye `save` les daría acceso a operaciones que no les corresponden y les obligaría a
implementarlas al construir un doble de prueba.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.enrollment import Enrollment


class EnrollmentReader(ABC):
    """Contrato de consulta de inscripciones."""

    @abstractmethod
    def find_by_id(self, enrollment_id: UUID) -> Enrollment | None:
        """Recupera una inscripción por su identificador.

        Args:
            enrollment_id: identificador de la inscripción.

        Returns:
            La inscripción, o `None` si no existe.
        """

    @abstractmethod
    def find_active_by_student(
        self, student_id: UUID, enrollment_period_id: UUID
    ) -> list[Enrollment]:
        """Recupera las inscripciones vigentes de un estudiante en un período.

        Solo las activas: las canceladas no ocupan cupo, no entran en el horario y no impiden
        una inscripción nueva en el mismo grupo. La resuelve el índice parcial
        `ix_enrollments_active`.

        Args:
            student_id: identificador del estudiante.
            enrollment_period_id: período sobre el que consultar.

        Returns:
            Las inscripciones activas, o una lista vacía.
        """

    @abstractmethod
    def find_by_student_and_offering(
        self, student_id: UUID, course_offering_id: UUID, enrollment_period_id: UUID
    ) -> Enrollment | None:
        """Recupera la inscripción de un estudiante en un grupo concreto.

        Incluye las canceladas a propósito. La restricción `UNIQUE` de la tabla impide crear
        una fila nueva cuando alguien cancela y se reinscribe en el mismo grupo, así que el
        caso de uso necesita encontrar la existente para reactivarla en vez de intentar un
        `INSERT` que fallaría.

        Args:
            student_id: identificador del estudiante.
            course_offering_id: identificador del grupo.
            enrollment_period_id: período vigente.

        Returns:
            La inscripción, activa o cancelada, o `None` si nunca existió.
        """


class EnrollmentWriter(ABC):
    """Contrato de escritura de inscripciones."""

    @abstractmethod
    def save(self, enrollment: Enrollment) -> None:
        """Persiste una inscripción nueva o los cambios de una existente.

        No confirma la transacción: eso lo decide el `UnitOfWork` que envuelve la operación.
        Una escritura que se confirmara sola rompería la atomicidad con el descuento de cupo.

        Args:
            enrollment: la entidad a persistir.
        """


class EnrollmentRepository(EnrollmentReader, EnrollmentWriter):
    """Contrato completo, para quien necesita leer y escribir.

    Lo usa el caso de uso de inscripción, que comprueba si ya existe una inscripción y después
    la crea o la reactiva.
    """
