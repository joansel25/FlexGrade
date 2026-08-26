"""Value object `HistoryStatus`: cómo terminó una materia en el expediente."""

from __future__ import annotations

from enum import Enum


class HistoryStatus(str, Enum):
    """Resultado consolidado de una materia, alineado con el CHECK de `academic_history.status`.

    - `APPROVED`: se aprobó. **Es el único que cuenta como prerrequisito.**
    - `FAILED`: se cursó y se perdió. Cuenta como intento en el expediente y no habilita nada.
    - `WITHDRAWN`: se retiró a mitad de semestre. Hoy ninguna operación lo produce: cancelar
      una inscripción la borra del semestre en curso en vez de dejar constancia, y esa decisión
      es de la Fase 3. Existe en el enum porque la columna lo admite y un expediente real lo
      necesita, pero **no se implementa por iniciativa propia**.
    """

    APPROVED = "APPROVED"
    FAILED = "FAILED"
    WITHDRAWN = "WITHDRAWN"
