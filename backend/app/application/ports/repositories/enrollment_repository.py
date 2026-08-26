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
    def find_by_offering(self, offering_id: UUID) -> list[Enrollment]:
        """Devuelve las inscripciones VIVAS de un grupo, en orden de inscripción.

        Las canceladas no salen: quien dio de baja la materia no la cursó, y sacarla en la lista
        del docente invitaría a calificar una fila que el dominio va a rechazar.
        """

    @abstractmethod
    def find_by_student_and_offering_any_status(
        self, student_id: UUID, offering_id: UUID
    ) -> Enrollment | None:
        """Devuelve la inscripción de un estudiante en un grupo, esté como esté.

        Se distingue de `find_by_student_and_offering`, que solo devuelve las vivas. Calificar
        necesita ver también las canceladas para poder decir «canceló la materia» —que es lo que
        pasó— en vez de «no está inscrito», que suena a error de tecleo.
        """

    @abstractmethod
    def count_active_in_program(
        self, *, course_id: UUID, program_id: UUID, enrollment_period_id: UUID
    ) -> int:
        """Cuenta las inscripciones vivas de una materia entre estudiantes de un programa.

        Filtra POR PROGRAMA y no solo por materia porque un requisito pertenece al plan de una
        carrera: `FIS101` puede exigir `MAT101` en Ingeniería y entrar como electiva sin nada que
        exigir en otra. Contar a todos los inscritos daría un número que no corresponde a la
        regla que se está editando, y llevaría a rechazar cambios que no afectan a nadie.

        La usa la edición de requisitos para saber a cuántas matrículas afectaría una regla
        nueva. Es un conteo, no una lista: quien administra decide con el número, y traer las
        filas para contarlas cargaría miles de inscripciones en memoria durante la matrícula.
        """

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
