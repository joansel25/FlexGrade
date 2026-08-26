"""Puerto de consulta de docentes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.professor import Professor


class ProfessorReader(ABC):
    """Contrato mínimo de acceso a los docentes.

    Sigue sin declarar un `find_by_id` completo, y no por descuido: nadie lo consume. La
    creación de un grupo solo comprueba que el docente exista, y el catálogo obtiene su nombre
    resuelto dentro del grupo desde `OfferingRepository`. Un puerto que declara más de lo que se
    usa obliga a los dobles de prueba a implementar métodos que nadie llama (`ARCHITECTURE.md`,
    segregación de interfaces).

    `find_by_user_id` entra en la Fase 9, cuando el docente pasa a ser un actor que entra al
    sistema: es la traducción de CUENTA a PERFIL, la misma que `StudentRepository` hace para el
    estudiante.
    """

    @abstractmethod
    def exists(self, professor_id: UUID) -> bool:
        """Indica si hay un docente registrado con ese identificador.

        Args:
            professor_id: identificador del docente.

        Returns:
            `True` si el docente existe.
        """

    @abstractmethod
    def find_by_user_id(self, user_id: UUID) -> Professor | None:
        """Devuelve el perfil del docente asociado a una cuenta.

        El token identifica una CUENTA y las notas se registran sobre un DOCENTE, que no son lo
        mismo: un administrador tiene cuenta y no dicta clase. Esta consulta es esa traducción.

        Args:
            user_id: identificador de la cuenta autenticada.

        Returns:
            El perfil, o `None` si la cuenta no tiene ninguno asociado.
        """
