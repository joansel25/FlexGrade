"""Caso de uso: ajustar el cupo total de un grupo."""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from app.application.ports.cache_service import CacheService
from app.application.ports.repositories.offering_repository import OfferingRepository
from app.application.ports.unit_of_work import UnitOfWork
from app.application.use_cases.catalog import catalog_cache
from app.domain.entities.course_offering import CourseOffering
from app.domain.exceptions.admin import CapacityBelowEnrolledError, ConcurrentOfferingUpdateError
from app.domain.exceptions.catalog import OfferingNotFoundError

# Tres intentos, no más. El bloqueo optimista por `version` solo falla si otra escritura tocó
# el grupo entre la lectura y el `UPDATE`, y aquí eso es excepcional: reintentar indefinidamente
# solo alargaría una petición que ya se puede repetir desde fuera con información completa.
_MAX_INTENTOS = 3


class AdjustOfferingCapacityUseCase:
    """Cambia el cupo total de un grupo, sin dejar fuera a quien ya está inscrito.

    Ampliar el cupo es la operación habitual —una materia con lista de espera a la que se le
    añaden diez sitios—; reducirlo solo se admite hasta el número de inscritos actuales.

    Es la única operación de administración que **invalida la caché**. La entrada
    `catalog:v1:offering:{id}` guarda `total_capacity`, así que sin invalidarla el catálogo
    seguiría mostrando el cupo viejo hasta que expirara el TTL, y con él unos cupos
    disponibles que no cuadran: `enrolled_count` se lee siempre en vivo, de modo que la resta
    mezclaría un dato fresco con uno caducado.
    """

    def __init__(
        self,
        offering_repository: OfferingRepository,
        unit_of_work: UnitOfWork,
        cache: CacheService,
    ) -> None:
        self._offerings = offering_repository
        self._uow = unit_of_work
        self._cache = cache

    def execute(self, offering_id: UUID, *, total_capacity: int) -> CourseOffering:
        """Ajusta el cupo del grupo.

        Args:
            offering_id: identificador del grupo.
            total_capacity: cupo total que se quiere dejar; tiene que ser positivo.

        Returns:
            El grupo con su cupo ya ajustado.

        Raises:
            OfferingNotFoundError: si el grupo no existe.
            CapacityBelowEnrolledError: si el cupo pedido es menor que los inscritos actuales.
            ConcurrentOfferingUpdateError: si el grupo cambió en cada uno de los intentos.
        """
        for _ in range(_MAX_INTENTOS):
            with self._uow:
                grupo = self._offerings.find_by_id(offering_id)

                if grupo is None:
                    raise OfferingNotFoundError(offering_id)

                # Se comprueba antes de escribir para poder decir cuántos hay inscritos. El
                # `UPDATE` repite la condición, porque entre esta lectura y la escritura pueden
                # entrar inscripciones nuevas; ahí ya no hay nada que explicar, solo que no se
                # aplique.
                if total_capacity < grupo.enrolled_count:
                    raise CapacityBelowEnrolledError(
                        offering_id, total_capacity, grupo.enrolled_count
                    )

                aplicado = self._offerings.update_capacity(
                    offering_id,
                    new_capacity=total_capacity,
                    expected_version=grupo.version,
                )

                if not aplicado:
                    # Otra escritura ganó la carrera: se sale sin confirmar y se vuelve a leer.
                    # Reintentar con la versión vieja fallaría siempre igual.
                    continue

                self._uow.commit()

            # Fuera de la transacción y solo tras confirmarla, igual que en la inscripción: si
            # se invalidara dentro y la transacción se revirtiera, se habría borrado una entrada
            # correcta y la siguiente lectura repoblaría la caché con el valor viejo.
            self._cache.delete(catalog_cache.clave_grupo(offering_id))

            return replace(grupo, total_capacity=total_capacity, version=grupo.version + 1)

        raise ConcurrentOfferingUpdateError(offering_id)
