"""Caso de uso: listar el catálogo de materias con filtros y paginación."""

from __future__ import annotations

from uuid import UUID

from app.application.dtos.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, Page
from app.application.ports.repositories.course_repository import CourseRepository
from app.domain.entities.course import Course


class ListCoursesUseCase:
    """Devuelve una página del catálogo aplicando los filtros que llegan del cliente."""

    def __init__(self, course_repository: CourseRepository) -> None:
        self._course_repository = course_repository

    def execute(
        self,
        *,
        page: int = 1,
        size: int = DEFAULT_PAGE_SIZE,
        program_id: UUID | None = None,
        semester: int | None = None,
        search: str | None = None,
    ) -> Page[Course]:
        """Busca materias del catálogo.

        Los parámetros de paginación se sanean aquí y no en el router: son una regla de la
        aplicación, no del transporte HTTP, y cualquier otro punto de entrada —un comando de
        consola, una tarea programada— debe obtener el mismo comportamiento.

        Args:
            page: número de página. Un valor menor que 1 se trata como la primera.
            size: tamaño de página. Se acota a `MAX_PAGE_SIZE`; sin ese techo, un `?size=100000`
                sería una forma trivial de tumbar la base de datos durante el pico.
            program_id: si se indica, solo las materias del plan de ese programa.
            semester: si se indica, solo las del semestre sugerido correspondiente.
            search: si se indica, busca el texto en el nombre o el código de la materia.

        Returns:
            La página de materias y el total de coincidencias.
        """
        return self._course_repository.search(
            page=max(1, page),
            size=min(max(1, size), MAX_PAGE_SIZE),
            program_id=program_id,
            semester=semester,
            search=search,
        )
