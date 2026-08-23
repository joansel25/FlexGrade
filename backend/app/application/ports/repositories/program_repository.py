"""Puerto de persistencia del agregado Program."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.program import Program


class ProgramRepository(ABC):
    """Contrato de acceso a los programas académicos."""

    @abstractmethod
    def find_by_id(self, program_id: UUID) -> Program | None:
        """Recupera un programa por su identificador.

        Resuelve el bloque `program` anidado de `GET /students/me`, que la Fase 1 dejó como
        `program_id` plano precisamente por no existir todavía este repositorio.

        Args:
            program_id: identificador del programa.

        Returns:
            El programa, o `None` si no existe.
        """

    @abstractmethod
    def find_all(self) -> list[Program]:
        """Recupera todos los programas de la institución.

        Sin paginar a propósito: son unidades académicas completas, del orden de decenas, y
        no crecen con el uso del sistema. Alimenta el filtro por programa del catálogo.

        Returns:
            Los programas ordenados por código.
        """
