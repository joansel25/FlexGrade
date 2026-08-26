"""DTO del cierre de un período (iteración 9.3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class ConsolidationDTO:
    """Resumen de lo que escribió una consolidación.

    Devuelve CIFRAS y no la lista de registros. Un semestre son miles de filas, y quien acaba de
    cerrar el período no las va a leer: lo que necesita es confirmar de un vistazo que el número
    cuadra con lo que esperaba, porque la operación no se puede deshacer y ese es el último
    momento en que un error se detecta a tiempo para arreglarlo por otra vía.

    Attributes:
        period_id: la ventana cerrada.
        period_code: su código, para poder nombrarla sin otra consulta.
        academic_period: el semestre bajo el que quedaron las materias en el expediente.
        consolidated_at: el instante del cierre.
        records: cuántas filas se escribieron en el historial.
        approved: cuántas de ellas quedaron aprobadas. Junto con `records` da la tasa de
            aprobación del semestre, que es la primera cifra que se mira al cerrar.
    """

    period_id: UUID
    period_code: str
    academic_period: str
    consolidated_at: datetime
    records: int
    approved: int
