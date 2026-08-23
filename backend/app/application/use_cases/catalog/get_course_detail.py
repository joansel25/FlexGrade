"""Caso de uso: consultar el detalle de una materia y sus prerrequisitos."""

from __future__ import annotations

from uuid import UUID

from app.application.dtos.catalog_dto import CourseDetailDTO
from app.application.ports.repositories.course_repository import CourseRepository
from app.domain.exceptions.catalog import CourseNotFoundError


class GetCourseDetailUseCase:
    """Devuelve una materia junto con las que hay que haber aprobado antes."""

    def __init__(self, course_repository: CourseRepository) -> None:
        self._course_repository = course_repository

    def execute(self, course_id: UUID) -> CourseDetailDTO:
        """Consulta el detalle de una materia.

        Args:
            course_id: identificador de la materia.

        Returns:
            La materia y sus prerrequisitos directos.

        Raises:
            CourseNotFoundError: si la materia no existe.
        """
        materia = self._course_repository.find_by_id(course_id)

        if materia is None:
            raise CourseNotFoundError(course_id)

        # Solo se consultan los prerrequisitos DESPUÉS de confirmar que la materia existe:
        # al revés se haría una consulta inútil en el caso de error.
        prerrequisitos = self._course_repository.find_prerequisites(course_id)

        return CourseDetailDTO(course=materia, prerequisites=prerrequisitos)
