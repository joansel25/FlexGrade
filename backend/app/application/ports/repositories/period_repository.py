"""Puerto de persistencia del agregado EnrollmentPeriod."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.enrollment_period import EnrollmentPeriod


class PeriodRepository(ABC):
    """Contrato de acceso a las ventanas de matrícula.

    No se segrega en lector y escritor como `EnrollmentRepository`: solo hay un consumidor que
    escribe —la administración— y separarlo daría dos interfaces de un método cada una sin que
    nadie se beneficie. La segregación resuelve un problema real cuando existe un caso de uso
    de solo lectura que se vería obligado a depender de operaciones de escritura; aquí no lo
    hay.
    """

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

    @abstractmethod
    def find_by_code(self, code: str) -> EnrollmentPeriod | None:
        """Recupera una ventana por su código.

        Es la comprobación que evita chocar contra la restricción `UNIQUE` al crear: sin ella,
        crear un período repetido devolvería un error de clave duplicada de PostgreSQL en vez
        de un mensaje que diga qué pasó.

        Args:
            code: código de la ventana (por ejemplo `2026-1-V1`).

        Returns:
            El período, o `None` si no existe.
        """

    @abstractmethod
    def save(self, period: EnrollmentPeriod) -> None:
        """Persiste una ventana nueva o los cambios de una existente.

        No confirma la transacción: eso lo decide el `UnitOfWork`. Activar un período implica
        desactivar el anterior, y las dos escrituras tienen que ser atómicas —el índice único
        parcial rechazaría el estado intermedio con dos activos—.

        Args:
            period: la entidad a persistir.
        """
