"""Puerto de persistencia del agregado EnrollmentPeriod."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.enrollment_period import EnrollmentPeriod


class PeriodRepository(ABC):
    """Contrato de acceso a las ventanas de matrícula."""

    @abstractmethod
    def find_active(self) -> EnrollmentPeriod | None:
        """Recupera la ventana de matrícula marcada como activa.

        Es la consulta más frecuente del sistema: la ejecutan el catálogo de grupos y cada
        intento de inscripción. La resuelve el índice parcial `ix_enrollment_periods_active`.

        Devuelve la ventana **activa**, no necesariamente **abierta**: quién decide si admite
        inscripciones ahora mismo es `EnrollmentPeriod.is_open()`, comparando las fechas
        contra el instante actual. Separarlo permite mostrar al estudiante "la matrícula abre
        el martes" en vez de un simple "no hay período".

        Returns:
            La ventana activa, o `None` si no hay ninguna.
        """

    @abstractmethod
    def find_by_id(self, period_id: UUID) -> EnrollmentPeriod | None:
        """Recupera una ventana por su identificador.

        Args:
            period_id: identificador del período.

        Returns:
            El período, o `None` si no existe.
        """
