"""Caso de uso: consultar el detalle de un grupo."""

from __future__ import annotations

from uuid import UUID

from app.application.ports.cache_service import CacheService
from app.application.ports.repositories.offering_repository import OfferingRepository
from app.application.use_cases.catalog import catalog_cache
from app.domain.entities.course_offering import CourseOffering
from app.domain.exceptions.catalog import OfferingNotFoundError


class GetOfferingDetailUseCase:
    """Devuelve un grupo con su docente, su horario y su cupo real.

    Aquí se resuelve la única contradicción que había entre los documentos del proyecto.
    `API.md` pide cachear este endpoint 30 segundos porque durante la ventana de matrícula se
    consulta sin descanso; `CLAUDE.md` y `DATA_MODEL.md` prohíben cachear la disponibilidad de
    cupos. Las dos reglas tienen razón, y se cumplen partiendo el grupo en dos:

    - **Lo estático** —materia, docente, horario, capacidad total— cambia como mucho una vez
      por semestre. Se sirve desde Redis.
    - **`enrolled_count`** cambia miles de veces durante la ventana. Se lee SIEMPRE de
      PostgreSQL, con una consulta de una sola columna, aunque el resto venga de la caché.

    Un `available_slots` de hace treinta segundos es exactamente el fallo que este sistema
    existe para impedir: mostraría cupos libres en un grupo lleno y llevaría al estudiante a
    un 409 después de creer que tenía plaza.
    """

    def __init__(
        self,
        offering_repository: OfferingRepository,
        cache: CacheService,
        ttl_seconds: int,
    ) -> None:
        self._offering_repository = offering_repository
        self._cache = cache
        self._ttl_seconds = ttl_seconds

    def execute(self, offering_id: UUID) -> CourseOffering:
        """Consulta el detalle de un grupo.

        Args:
            offering_id: identificador del grupo.

        Returns:
            El grupo completo, con el cupo ocupado al día.

        Raises:
            OfferingNotFoundError: si el grupo no existe.
        """
        grupo = self._desde_cache(offering_id)

        if grupo is None:
            grupo = self._offering_repository.find_by_id(offering_id)

            if grupo is None:
                raise OfferingNotFoundError(offering_id)

            self._guardar_en_cache(grupo)

        # SIEMPRE, venga de donde venga el grupo. Cuando viene de la base de datos el valor ya
        # es correcto y esta lectura es redundante, pero hacerla en los dos caminos es lo que
        # garantiza que no exista ninguna ruta por la que se sirva un cupo cacheado. Cuesta
        # una consulta de una columna; equivocarse cuesta un sobrecupo aparente.
        ocupados = self._offering_repository.count_enrolled(offering_id)

        if ocupados is None:
            # El grupo se eliminó entre que se cacheó y ahora. La entrada obsoleta se
            # invalida para que la siguiente petición no repita el mismo camino inútil.
            self._cache.delete(catalog_cache.clave_grupo(offering_id))
            raise OfferingNotFoundError(offering_id)

        grupo.enrolled_count = ocupados
        return grupo

    # ------------------------------------------------------------------ helpers

    def _desde_cache(self, offering_id: UUID) -> CourseOffering | None:
        contenido = self._cache.get(catalog_cache.clave_grupo(offering_id))
        return None if contenido is None else catalog_cache.grupo_desde_json(contenido)

    def _guardar_en_cache(self, grupo: CourseOffering) -> None:
        self._cache.set(
            catalog_cache.clave_grupo(grupo.id),
            catalog_cache.grupo_a_json(grupo),
            self._ttl_seconds,
        )
