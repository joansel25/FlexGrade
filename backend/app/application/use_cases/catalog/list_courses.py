"""Caso de uso: listar el catálogo de materias con filtros y paginación."""

from __future__ import annotations

from uuid import UUID

from app.application.dtos.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, Page
from app.application.ports.cache_service import CacheService
from app.application.ports.repositories.course_repository import CourseRepository
from app.application.use_cases.catalog import catalog_cache
from app.domain.entities.course import Course


class ListCoursesUseCase:
    """Devuelve una página del catálogo aplicando los filtros que llegan del cliente.

    Se cachea entero, sin partirlo como el detalle de un grupo: una materia no lleva ningún
    dato volátil —ni cupos, ni ocupación— así que servirla con treinta segundos de antigüedad
    no puede inducir a error a nadie. Es además la consulta que más se repite idéntica: miles
    de estudiantes abriendo la primera página del catálogo sin filtros.
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
        # El saneado ocurre ANTES de construir la clave: si no, `?page=0` y `?page=-3` serían
        # dos entradas distintas de la caché con exactamente el mismo contenido.
        pagina = max(1, page)
        tamano = min(max(1, size), MAX_PAGE_SIZE)

        clave = catalog_cache.clave_listado(
            page=pagina, size=tamano, program_id=program_id, semester=semester, search=search
        )

        contenido = self._cache.get(clave)

        if contenido is not None:
            cacheado = catalog_cache.materias_desde_json(contenido)
            if cacheado is not None:
                materias, total = cacheado
                return Page(items=materias, total=total, page=pagina, size=tamano)

        resultado = self._course_repository.search(
            page=pagina,
            size=tamano,
            program_id=program_id,
            semester=semester,
            search=search,
        )

        self._cache.set(
            clave,
            catalog_cache.materias_a_json(list(resultado.items), resultado.total),
            self._ttl_seconds,
        )

        return resultado
