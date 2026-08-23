"""Puerto de persistencia del agregado CourseOffering."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.course_offering import CourseOffering


class OfferingRepository(ABC):
    """Contrato de acceso a los grupos de una materia.

    Todos los métodos devuelven el grupo **completo**: con su docente y sus franjas de
    horario ya resueltos. El adaptador es responsable de hacerlo en una sola consulta; un
    caso de uso nunca debe recorrer una lista de grupos pidiendo sus horarios uno a uno.
    """

    @abstractmethod
    def find_by_id(self, offering_id: UUID) -> CourseOffering | None:
        """Recupera un grupo por su identificador.

        Args:
            offering_id: identificador del grupo.

        Returns:
            El grupo, o `None` si no existe.
        """

    @abstractmethod
    def find_by_course_and_period(
        self, course_id: UUID, enrollment_period_id: UUID
    ) -> list[CourseOffering]:
        """Recupera los grupos de una materia dentro de un período.

        Es la consulta que resuelve `GET /courses/{id}/offerings`.

        Args:
            course_id: identificador de la materia.
            enrollment_period_id: identificador del período de matrícula.

        Returns:
            Los grupos ordenados por número de grupo, o una lista vacía si la materia no se
            ofrece en ese período.
        """

    @abstractmethod
    def count_enrolled(self, offering_id: UUID) -> int | None:
        """Lee el número de cupos ocupados directamente de la base de datos.

        Existe separado de `find_by_id` por una razón concreta: la disponibilidad de cupos
        **nunca se cachea** (`CLAUDE.md`). El resto del grupo —materia, docente, horario,
        capacidad— cambia una vez por semestre y se cachea sin problema, pero
        `enrolled_count` cambia miles de veces durante la ventana de matrícula. Este método
        permite servir la parte estática desde la caché y refrescar solo el contador con una
        lectura mínima a PostgreSQL.

        Args:
            offering_id: identificador del grupo.

        Returns:
            Los cupos ocupados, o `None` si el grupo ya no existe.
        """
