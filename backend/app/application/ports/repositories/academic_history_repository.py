"""Puerto de consulta del historial académico.

Solo de lectura. El historial lo escriben los procesos de cierre de semestre, que están fuera
del alcance del sistema de matrícula: aquí únicamente se consulta para decidir si alguien
cumple los prerrequisitos de una materia.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from app.domain.entities.academic_record import AcademicRecord


class AcademicHistoryReader(ABC):
    """Contrato de acceso al historial académico.

    Se llamó `Reader` cuando solo se leía. Desde la iteración 9.3 también escribe: la
    consolidación del período es lo único que crea filas aquí, y es lo que cierra el ciclo
    `inscribir → cursar → calificar → consolidar → prerrequisito`. El nombre se conserva para no
    tocar cuarenta puntos de importación por una palabra.
    """

    @abstractmethod
    def find_approved_course_ids(self, student_id: UUID) -> set[UUID]:
        """Devuelve las materias que el estudiante tiene APROBADAS.

        Solo `APPROVED` cuenta: una materia perdida o retirada no habilita nada. La consulta la
        resuelve el índice `ix_history_student_status`, que existe precisamente para esta
        pregunta, la que corre en cada intento de inscripción durante el pico.

        Devuelve un conjunto y no una lista porque quien lo usa solo pregunta por pertenencia, y
        el historial de un estudiante avanzado puede tener decenas de entradas.

        Args:
            student_id: identificador del estudiante.

        Returns:
            Los identificadores de las materias aprobadas. Vacío si no cursó nada todavía.
        """

    @abstractmethod
    def find_recorded_courses(
        self, student_ids: Sequence[UUID], academic_period: str
    ) -> set[tuple[UUID, UUID]]:
        """Qué parejas (estudiante, materia) ya constan en el historial de ese semestre.

        Existe para que la consolidación pueda RECHAZAR nombrando el choque en vez de dejar que
        salte el `UNIQUE` a mitad de una transacción que escribe miles de filas. Un error de
        restricción no dice cuál de todas la rompió.

        El caso real son dos ventanas de matrícula que comparten `academic_period` —primera y
        segunda vuelta del mismo semestre— con alguien que cursó la misma materia en las dos.
        """

    @abstractmethod
    def save_all(self, records: Sequence[AcademicRecord]) -> None:
        """Escribe de golpe los registros de una consolidación.

        En bloque y no uno a uno: un semestre son miles de filas, y otras tantas idas y vueltas
        a la base dentro de una sola transacción la alargarían lo suficiente como para competir
        con la matrícula del semestre siguiente.

        No confirma la transacción: eso lo decide el `UnitOfWork`. Es lo que garantiza que el
        expediente y la marca de consolidación se escriban juntos o no se escriba ninguno.
        """
