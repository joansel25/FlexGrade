"""Puerto de persistencia del agregado Course."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.application.dtos.pagination import Page
from app.domain.entities.course import Course
from app.domain.value_objects.course_code import CourseCode


class CourseRepository(ABC):
    """Contrato de acceso al catálogo de materias."""

    @abstractmethod
    def find_by_id(self, course_id: UUID) -> Course | None:
        """Recupera una materia por su identificador.

        Args:
            course_id: identificador de la materia.

        Returns:
            La materia, o `None` si no existe.
        """

    @abstractmethod
    def find_by_code(self, code: CourseCode) -> Course | None:
        """Recupera una materia por su código institucional.

        Args:
            code: código de la materia (por ejemplo `MAT101`).

        Returns:
            La materia, o `None` si no existe.
        """

    @abstractmethod
    def find_prerequisites(self, course_id: UUID) -> list[Course]:
        """Recupera las materias que hay que haber aprobado antes de cursar esta.

        Devuelve solo los prerrequisitos **directos**, no el cierre transitivo: si B exige A
        y C exige B, consultar los de C devuelve solo B. Es lo que pide el contrato de
        `GET /courses/{id}` y lo que necesita la validación de la Fase 3, que comprueba nivel
        a nivel.

        Args:
            course_id: identificador de la materia.

        Returns:
            Los prerrequisitos directos, o una lista vacía si no tiene.
        """

    @abstractmethod
    def belongs_to_program(self, course_id: UUID, program_id: UUID) -> bool:
        """Indica si la materia forma parte del plan de estudios de un programa.

        Es lo que sostiene el `403 COURSE_NOT_IN_PROGRAM` de `API.md`: un estudiante de Derecho
        no debe poder inscribir Programación II, aunque la materia exista y tenga cupo.

        Args:
            course_id: identificador de la materia.
            program_id: programa contra el que comprobar.

        Returns:
            `True` si la materia está en ese plan de estudios.
        """

    @abstractmethod
    def search(
        self,
        *,
        page: int,
        size: int,
        program_id: UUID | None = None,
        semester: int | None = None,
        search: str | None = None,
    ) -> Page[Course]:
        """Busca materias del catálogo aplicando los filtros de `GET /courses`.

        Los filtros son acumulativos y todos opcionales: sin ninguno devuelve el catálogo
        completo paginado.

        Args:
            page: número de página, empezando en 1.
            size: cuántas materias por página.
            program_id: si se indica, solo las materias del plan de estudios de ese programa.
            semester: si se indica, solo las materias cuyo semestre sugerido coincida. Depende
                del plan de estudios, así que solo tiene sentido junto a `program_id`; sin él,
                filtra por las materias que estén sugeridas en ese semestre en cualquier plan.
            search: si se indica, busca el texto en el nombre o en el código de la materia,
                sin distinguir mayúsculas.

        Returns:
            La página de resultados y el total de coincidencias.
        """
