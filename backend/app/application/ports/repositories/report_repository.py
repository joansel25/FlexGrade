"""Puerto de consulta de los reportes de administración.

Es un puerto de **solo lectura y solo agregados**. No devuelve entidades porque no las hay: sus
respuestas cruzan `enrollments`, `students`, `programs` y `course_offerings` para producir
cifras que no pertenecen a ningún agregado del dominio.

Cada método es una consulta agregada que resuelve PostgreSQL con `GROUP BY`. Traer las filas y
contarlas en Python daría el mismo número, pero moviendo miles de registros por la red en el
momento de mayor carga del sistema para descartarlos justo después.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.application.dtos.pagination import Page
from app.application.dtos.report_dto import (
    OfferingOccupancyDTO,
    ProgramEnrollmentsDTO,
    ReportTotalsDTO,
)


class ReportReader(ABC):
    """Contrato de las consultas agregadas de administración."""

    @abstractmethod
    def enrollment_totals(self, enrollment_period_id: UUID) -> ReportTotalsDTO:
        """Calcula las cifras globales de inscripción del período.

        Cuenta filas reales de `enrollments` con estado `ENROLLED`, no el contador
        desnormalizado `course_offerings.enrolled_count`. Son dos fuentes que la transacción de
        inscripción mantiene de acuerdo, y usar aquí la primera convierte al reporte en la
        forma de detectar si alguna vez dejaran de estarlo.

        Args:
            enrollment_period_id: ventana de matrícula sobre la que calcular.

        Returns:
            Las cifras globales. Un período sin inscripciones devuelve ceros, no `None`: cero
            es una respuesta legítima del reporte.
        """

    @abstractmethod
    def enrollments_by_program(self, enrollment_period_id: UUID) -> list[ProgramEnrollmentsDTO]:
        """Desglosa las inscripciones activas del período por programa académico.

        Sin paginar: los programas de una institución son del orden de decenas y no crecen con
        el uso, igual que en `ProgramRepository.find_all`.

        Args:
            enrollment_period_id: ventana de matrícula sobre la que calcular.

        Returns:
            Los programas con al menos una inscripción activa, del que más tiene al que menos.
            Un programa sin inscripciones no aparece: el reporte informa de lo que ocurrió, y
            una fila de ceros por cada programa sin actividad solo añadiría ruido.
        """

    @abstractmethod
    def offering_occupancy(
        self, enrollment_period_id: UUID, *, page: int, size: int
    ) -> Page[OfferingOccupancyDTO]:
        """Lista la ocupación de los grupos del período, del más lleno al más vacío.

        Va paginado aunque `API.md` no lo pida, y la razón es de tamaño: el período de una
        institución con 5.000 estudiantes tiene cientos de grupos, y una respuesta sin límite
        crecería sin control con cada semestre. El orden por ocupación descendente hace además
        que la primera página sea justo la que se consulta —los grupos a punto de llenarse—.

        Usa `course_offerings.enrolled_count` y no un `COUNT` sobre `enrollments`: es el mismo
        contador que decide si queda cupo, así que el reporte muestra exactamente el número
        contra el que se está compitiendo, y la consulta no toca la tabla más caliente del
        sistema durante el pico.

        Args:
            enrollment_period_id: ventana de matrícula sobre la que calcular.
            page: número de página, empezando en 1.
            size: cuántos grupos por página.

        Returns:
            La página de grupos y el total del período.
        """
