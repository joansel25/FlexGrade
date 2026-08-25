"""Caso de uso: consultar el detalle de una materia y sus prerrequisitos."""

from __future__ import annotations

from uuid import UUID

from app.application.dtos.catalog_dto import CourseDetailDTO
from app.application.ports.cache_service import CacheService
from app.application.ports.repositories.course_repository import CourseRepository
from app.application.use_cases.catalog import catalog_cache
from app.domain.exceptions.catalog import CourseNotFoundError


class GetCourseDetailUseCase:
    """Devuelve una materia junto con lo que exige dentro de un plan de estudios.

    EL PLAN ES OBLIGATORIO PARA RESPONDER LOS REQUISITOS, y por eso `program_id` es un
    parámetro y no un filtro. Desde la iteración 6.2 un prerrequisito no une dos materias sino
    dos materias dentro de una carrera, así que «qué exige MAT102» no tiene una respuesta
    única: puede exigir MAT101 en Ingeniería y nada en otro plan donde entre como electiva.
    Sin programa se devuelve la materia con las dos listas vacías, y `program_id` vuelve en
    `None` para que quede claro que nadie preguntó, en vez de afirmar que no exige nada.

    Se decidió eso y no devolver la unión de todos los planes: esa unión no es cierta en
    ninguna carrera concreta, y a un estudiante de Derecho le mostraría los requisitos de
    Ingeniería como si fueran suyos.

    Se cachea solo la materia, no sus requisitos. Podrían cachearse juntos, pero eso obligaría
    a una clave por programa y a un segundo formato de serialización para ahorrar una consulta
    a una tabla diminuta que se lee por el prefijo de su clave primaria. La materia sí se
    reutiliza: la misma entrada de caché sirve a este endpoint y a cualquier otro que necesite
    la materia por su identificador.
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

    def execute(self, course_id: UUID, program_id: UUID | None = None) -> CourseDetailDTO:
        """Consulta el detalle de una materia.

        Args:
            course_id: identificador de la materia.
            program_id: plan de estudios sobre el que resolver los requisitos. Sin él, las
                dos listas vuelven vacías.

        Returns:
            La materia y, si se indicó un plan, sus prerrequisitos y correquisitos directos.

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

        if program_id is None:
            return CourseDetailDTO(course=materia)

        # Solo se consultan los requisitos DESPUÉS de confirmar que la materia existe: al revés
        # se haría una consulta inútil en el caso de error.
        requisitos = self._course_repository.find_requirements(course_id, program_id)

        return CourseDetailDTO(
            course=materia,
            program_id=program_id,
            prerequisites=[r.course for r in requisitos if r.is_prerequisite()],
            corequisites=[r.course for r in requisitos if r.is_corequisite()],
        )
