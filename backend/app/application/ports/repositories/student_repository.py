"""Puerto de persistencia del agregado Student."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.student import Student
from app.domain.value_objects.student_code import StudentCode


class StudentRepository(ABC):
    """Contrato de acceso a los perfiles académicos de los estudiantes."""

    @abstractmethod
    def find_by_id(self, student_id: UUID) -> Student | None:
        """Recupera un perfil por su identificador.

        Args:
            student_id: identificador del perfil.

        Returns:
            El perfil, o `None` si no existe.
        """

    @abstractmethod
    def find_by_user_id(self, user_id: UUID) -> Student | None:
        """Recupera el perfil asociado a una cuenta de autenticación.

        Es la consulta que resuelve `GET /students/me`: del token sale el
        `user_id`, y de aquí el perfil académico correspondiente.

        Args:
            user_id: identificador de la cuenta.

        Returns:
            El perfil, o `None` si la cuenta no es de un estudiante.
        """

    @abstractmethod
    def find_by_student_code(self, student_code: StudentCode) -> Student | None:
        """Recupera un perfil por su código institucional.

        Args:
            student_code: código institucional del estudiante.

        Returns:
            El perfil, o `None` si no existe.
        """

    @abstractmethod
    def save(self, student: Student) -> None:
        """Persiste un perfil nuevo o los cambios de uno existente.

        Args:
            student: la entidad a persistir.
        """
