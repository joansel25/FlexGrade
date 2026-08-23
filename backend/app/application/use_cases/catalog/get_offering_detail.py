"""Caso de uso: consultar el detalle de un grupo."""

from __future__ import annotations

from uuid import UUID

from app.application.ports.repositories.offering_repository import OfferingRepository
from app.domain.entities.course_offering import CourseOffering
from app.domain.exceptions.catalog import OfferingNotFoundError


class GetOfferingDetailUseCase:
    """Devuelve un grupo con su docente, su horario y su cupo.

    La caché de este endpoint llega en la iteración 2.4, y vivirá aquí dentro y no en el
    router: `CacheService` es un puerto de la capa de aplicación, y la regla de qué se cachea
    y qué no es una decisión de negocio. El grupo se servirá desde Redis en su parte estática
    —materia, docente, horario, capacidad— mientras que `enrolled_count` se releerá siempre de
    PostgreSQL con `OfferingRepository.count_enrolled`, porque la disponibilidad de cupos
    nunca se cachea.
    """

    def __init__(self, offering_repository: OfferingRepository) -> None:
        self._offering_repository = offering_repository

    def execute(self, offering_id: UUID) -> CourseOffering:
        """Consulta el detalle de un grupo.

        Args:
            offering_id: identificador del grupo.

        Returns:
            El grupo completo, con su docente y sus franjas de horario resueltos.

        Raises:
            OfferingNotFoundError: si el grupo no existe.
        """
        grupo = self._offering_repository.find_by_id(offering_id)

        if grupo is None:
            raise OfferingNotFoundError(offering_id)

        return grupo
