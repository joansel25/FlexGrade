"""Caso de uso: consultar el detalle de una materia y sus prerrequisitos."""

from __future__ import annotations

from uuid import UUID

from app.application.dtos.catalog_dto import CourseDetailDTO
from app.application.ports.cache_service import CacheService
from app.application.ports.repositories.course_repository import CourseRepository
from app.application.use_cases.catalog import catalog_cache
from app.domain.exceptions.catalog import CourseNotFoundError


class GetCourseDetailUseCase:
    """Devuelve una materia junto con las que hay que haber aprobado antes.

    Se cachea solo la materia, no sus prerrequisitos. Podrían cachearse juntos, pero eso
    obligaría a un segundo formato de serialización para ahorrar una consulta a una tabla
    diminuta que se lee por clave primaria. La materia sí se reutiliza: la misma entrada de
    caché sirve a este endpoint y a cualquier otro que necesite la materia por su
    identificador.
    """

    def __init__(
        self,
        course_repository: CourseRepository,
        cache: CacheService,
        ttl_seconds: int,
    ) -> None:
        self._course_repository = course_repository
        self._cache = cache
        self._ttl_seconds = ttl_seconds

    def execute(self, course_id: UUID) -> CourseDetailDTO:
        """Consulta el detalle de una materia.

        Args:
            course_id: identificador de la materia.

        Returns:
            La materia y sus prerrequisitos directos.

        Raises:
            CourseNotFoundError: si la materia no existe.
        """
        clave = catalog_cache.clave_materia(course_id)
        contenido = self._cache.get(clave)
        materia = None if contenido is None else catalog_cache.materia_desde_json(contenido)

        if materia is None:
            materia = self._course_repository.find_by_id(course_id)

            if materia is None:
                raise CourseNotFoundError(course_id)

            self._cache.set(clave, catalog_cache.materia_a_json(materia), self._ttl_seconds)

        # Solo se consultan los prerrequisitos DESPUÉS de confirmar que la materia existe: al
        # revés se haría una consulta inútil en el caso de error.
        prerrequisitos = self._course_repository.find_prerequisites(course_id)

        return CourseDetailDTO(course=materia, prerequisites=prerrequisitos)
