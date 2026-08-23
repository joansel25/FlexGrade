"""Caso de uso: consultar los grupos de una materia en el período activo."""

from __future__ import annotations

from uuid import UUID

from app.application.dtos.catalog_dto import CourseOfferingsDTO
from app.application.ports.repositories.course_repository import CourseRepository
from app.application.ports.repositories.offering_repository import OfferingRepository
from app.application.ports.repositories.period_repository import PeriodRepository
from app.domain.exceptions.catalog import CourseNotFoundError, NoActivePeriodError


class GetCourseOfferingsUseCase:
    """Devuelve los grupos abiertos de una materia en la ventana de matrícula vigente."""

    def __init__(
        self,
        course_repository: CourseRepository,
        offering_repository: OfferingRepository,
        period_repository: PeriodRepository,
    ) -> None:
        self._course_repository = course_repository
        self._offering_repository = offering_repository
        self._period_repository = period_repository

    def execute(self, course_id: UUID) -> CourseOfferingsDTO:
        """Consulta los grupos de una materia.

        El período no lo elige el cliente: es siempre el activo. Dejar que llegara por
        parámetro permitiría consultar la oferta de semestres cerrados y, peor, inscribirse
        contra ellos cuando la Fase 3 reutilice este camino.

        Args:
            course_id: identificador de la materia.

        Returns:
            La materia, el período activo y sus grupos. La lista de grupos va vacía si la
            materia existe pero no se ofrece este semestre, que es un resultado legítimo y no
            un error.

        Raises:
            CourseNotFoundError: si la materia no existe.
            NoActivePeriodError: si no hay ninguna ventana de matrícula activa.
        """
        materia = self._course_repository.find_by_id(course_id)

        if materia is None:
            raise CourseNotFoundError(course_id)

        periodo = self._period_repository.find_active()

        if periodo is None:
            raise NoActivePeriodError()

        grupos = self._offering_repository.find_by_course_and_period(course_id, periodo.id)

        return CourseOfferingsDTO(course=materia, period=periodo, offerings=grupos)
