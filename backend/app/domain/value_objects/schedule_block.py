"""Value object de una franja horaria semanal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from app.domain.exceptions.invalid_value import InvalidScheduleBlockError

_DIA_MINIMO = 1  # lunes, según ISO 8601
_DIA_MAXIMO = 7  # domingo


@dataclass(frozen=True)
class ScheduleBlock:
    """Una franja de clase: un día de la semana con hora de inicio y de fin.

    No lleva identificador aunque la tabla `schedule_blocks` sí lo tenga: en el dominio una
    franja no tiene identidad propia, es un componente del grupo que la contiene. Dos franjas
    con el mismo día y las mismas horas son la misma franja, que es exactamente la semántica
    de un value object.

    Es la pieza sobre la que se apoyará `ScheduleConflictDetector` en la Fase 3.

    Attributes:
        day_of_week: día de la semana, de 1 (lunes) a 7 (domingo).
        start_time: hora de inicio. Sin zona horaria: es una hora de calendario académico,
            no un instante absoluto.
        end_time: hora de fin, siempre posterior al inicio.
        classroom: aula asignada, si ya se conoce.
    """

    day_of_week: int
    start_time: time
    end_time: time
    classroom: str | None = None

    def __post_init__(self) -> None:
        if not _DIA_MINIMO <= self.day_of_week <= _DIA_MAXIMO:
            raise InvalidScheduleBlockError(
                f"El día '{self.day_of_week}' está fuera de rango "
                f"({_DIA_MINIMO} = lunes, {_DIA_MAXIMO} = domingo)"
            )

        if self.end_time <= self.start_time:
            raise InvalidScheduleBlockError(
                f"La hora de fin ({self.end_time}) debe ser posterior "
                f"a la de inicio ({self.start_time})"
            )

    def overlaps(self, other: ScheduleBlock) -> bool:
        """Indica si esta franja se solapa con otra.

        Dos franjas se solapan si caen el mismo día y sus intervalos se cruzan. El cruce se
        comprueba con `inicio_a < fin_b and inicio_b < fin_a`, que es estricto a propósito:
        una clase que termina a las 10:00 y otra que empieza a las 10:00 **no** chocan, son
        consecutivas. Usar `<=` marcaría como conflicto un horario perfectamente válido.

        Args:
            other: la otra franja a comparar.

        Returns:
            `True` si las dos franjas no pueden cursarse a la vez.
        """
        if self.day_of_week != other.day_of_week:
            return False

        return self.start_time < other.end_time and other.start_time < self.end_time
