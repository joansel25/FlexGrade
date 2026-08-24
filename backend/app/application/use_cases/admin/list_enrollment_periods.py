"""Caso de uso: listar las ventanas de matrícula."""

from __future__ import annotations

from app.application.dtos.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, Page
from app.application.ports.repositories.period_repository import PeriodRepository
from app.domain.entities.enrollment_period import EnrollmentPeriod


class ListEnrollmentPeriodsUseCase:
    """Devuelve las ventanas de matrícula, de la más reciente a la más antigua.

    Existe porque activar una ventana exige conocer su identificador. Sin este listado, el
    único modo de obtenerlo sería copiarlo de la respuesta de creación, lo que obliga a no
    perderla y deja sin manejar las ventanas creadas en otro momento.
    """

    def __init__(self, period_repository: PeriodRepository) -> None:
        self._periods = period_repository

    def execute(self, *, page: int = 1, size: int = DEFAULT_PAGE_SIZE) -> Page[EnrollmentPeriod]:
        """Lista las ventanas.

        El saneado de la paginación vive aquí y no en el router, igual que en el catálogo: es
        una regla de la aplicación, y cualquier otro punto de entrada debe obtener el mismo
        comportamiento.

        Args:
            page: número de página. Un valor menor que 1 se trata como la primera.
            size: tamaño de página, acotado a `MAX_PAGE_SIZE`.

        Returns:
            La página de ventanas y el total.
        """
        return self._periods.list_all(
            page=max(1, page),
            size=min(max(1, size), MAX_PAGE_SIZE),
        )
