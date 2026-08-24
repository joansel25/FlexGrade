"""Caso de uso: cancelar una inscripción y liberar el cupo.

Es la operación inversa a inscribir, y comparte con ella la misma exigencia de atomicidad: el
cambio de estado de la inscripción y la liberación del cupo ocurren en una sola transacción. Si
una se aplicara sin la otra el sistema quedaría con un cupo ocupado que nadie usa —o, peor, con
uno libre de más que dos personas podrían tomar—.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from app.application.ports.cache_service import CacheService
from app.application.ports.repositories.enrollment_repository import EnrollmentRepository
from app.application.ports.repositories.offering_repository import OfferingRepository
from app.application.ports.unit_of_work import UnitOfWork
from app.application.use_cases.catalog import catalog_cache
from app.domain.exceptions.enrollment import EnrollmentNotFoundError

Clock = Callable[[], datetime]


def _reloj_del_sistema() -> datetime:
    """Instante actual en UTC. Toda fecha del sistema viaja en UTC (`API.md`)."""
    return datetime.now(UTC)


class CancelEnrollmentUseCase:
    """Cancela una inscripción propia y devuelve su cupo al grupo."""

    def __init__(
        self,
        enrollment_repository: EnrollmentRepository,
        offering_repository: OfferingRepository,
        unit_of_work: UnitOfWork,
        cache: CacheService,
        clock: Clock | None = None,
    ) -> None:
        self._enrollment_repository = enrollment_repository
        self._offering_repository = offering_repository
        self._uow = unit_of_work
        self._cache = cache
        self._clock = clock or _reloj_del_sistema

    def execute(self, *, student_id: UUID, enrollment_id: UUID) -> None:
        """Cancela la inscripción indicada.

        Args:
            student_id: quien pide la cancelación. Sale del token, nunca de la petición.
            enrollment_id: inscripción a cancelar.

        Raises:
            EnrollmentNotFoundError: si no existe **o si pertenece a otra persona**.
            EnrollmentAlreadyCancelledError: si ya estaba cancelada.
        """
        with self._uow:
            inscripcion = self._enrollment_repository.find_by_id(enrollment_id)

            # Se responde lo mismo cuando no existe y cuando es de otro. Es deliberado: decir
            # «esa inscripción no es tuya» confirmaría que ese identificador corresponde a una
            # real, y permitiría enumerarlas probando identificadores hasta dar con una.
            if inscripcion is None or inscripcion.student_id != student_id:
                raise EnrollmentNotFoundError(enrollment_id)

            # La entidad rechaza cancelar lo ya cancelado. Es la primera de las dos defensas
            # contra liberar el cupo dos veces; la segunda es la guarda de `try_release_slot`,
            # que nunca deja el contador por debajo de cero.
            inscripcion.cancel(self._clock())

            self._offering_repository.try_release_slot(inscripcion.course_offering_id)
            self._enrollment_repository.save(inscripcion)
            self._uow.commit()

        # Fuera de la transacción y solo tras confirmarla: invalidar antes dejaría a la
        # siguiente petición releyendo un estado que aún podría revertirse.
        self._cache.delete(catalog_cache.clave_grupo(inscripcion.course_offering_id))
