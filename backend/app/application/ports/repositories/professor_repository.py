"""Puerto de consulta de docentes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID


class ProfessorReader(ABC):
    """Contrato mínimo de acceso a los docentes.

    Declara solo `exists` y no un `find_by_id` completo porque es lo único que necesita quien
    lo usa: la creación de un grupo comprueba que el docente asignado existe y nada más. El
    catálogo, que sí muestra el nombre del docente, lo obtiene resuelto dentro del grupo desde
    `OfferingRepository`, sin pasar por aquí.

    Un puerto que declara más de lo que se consume obliga a los dobles de prueba a implementar
    métodos que nadie llama (`ARCHITECTURE.md`, segregación de interfaces).
    """

    @abstractmethod
    def exists(self, professor_id: UUID) -> bool:
        """Indica si hay un docente registrado con ese identificador.

        Args:
            professor_id: identificador del docente.

        Returns:
            `True` si el docente existe.
        """
