"""Puerto de consulta del historial académico.

Solo de lectura. El historial lo escriben los procesos de cierre de semestre, que están fuera
del alcance del sistema de matrícula: aquí únicamente se consulta para decidir si alguien
cumple los prerrequisitos de una materia.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID


class AcademicHistoryReader(ABC):
    """Contrato de consulta del historial académico de un estudiante."""

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
