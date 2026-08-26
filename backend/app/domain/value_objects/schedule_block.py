"""Value object de una franja horaria semanal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from app.domain.entities.space import Space
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

    Es la pieza sobre la que se apoya `ScheduleConflictDetector` desde la Fase 3, y sobre la
    que se apoyará la detección de doble reserva de espacios en la 7.2.

    Attributes:
        day_of_week: día de la semana, de 1 (lunes) a 7 (domingo).
        start_time: hora de inicio. Sin zona horaria: es una hora de calendario académico,
            no un instante absoluto.
        end_time: hora de fin, siempre posterior al inicio.
        space: espacio asignado, si ya se conoce. Es una ENTIDAD desde la iteración 7.1, no el
            texto que era antes: un texto no puede estar ocupado, y sin identidad no había
            forma de impedir que dos grupos reservaran el mismo salón a la misma hora.

    LA FRANJA SIGUE SIN TENER IDENTIDAD PROPIA aunque ahora apunte a una entidad. Dos franjas
    con el mismo día, las mismas horas y el mismo espacio son la misma franja; que el espacio
    sea una entidad no convierte en entidad a lo que la contiene. Por eso `Space` viaja aquí
    por referencia y la igualdad del value object la sigue decidiendo su contenido.
    """

    day_of_week: int
    start_time: time
    end_time: time
    space: Space | None = None

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

    @property
    def classroom(self) -> str | None:
        """Nombre del espacio asignado, o `None` si todavía no lo tiene.

        Existe para que las capas que solo van a IMPRIMIR el aula —el horario, el comprobante,
        la ficha de un grupo— no tengan que repetir `bloque.space.code if bloque.space else
        None` en cada una. Es el mismo dato que la API expuso siempre bajo ese nombre, así que
        el contrato público no cambia por dentro haberse convertido en una entidad.
        """
        return None if self.space is None else self.space.code

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
