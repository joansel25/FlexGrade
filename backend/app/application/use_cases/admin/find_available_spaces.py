"""Caso de uso: qué espacios están libres en una franja concreta."""

from __future__ import annotations

from datetime import time

from app.application.ports.repositories.period_repository import PeriodRepository
from app.application.ports.repositories.space_repository import SpaceReader
from app.domain.entities.space import Space
from app.domain.exceptions.catalog import NoActivePeriodError
from app.domain.exceptions.invalid_value import InvalidScheduleBlockError
from app.domain.value_objects.space_type import SpaceType


class FindAvailableSpacesUseCase:
    """Responde «qué aulas están libres el martes de 10 a 12 para cuarenta personas».

    Es lo que convierte la asignación de aulas de un ejercicio de memoria en una consulta. Sin
    esto, quien programa un grupo solo puede probar códigos contra `POST /admin/offerings` y
    dejar que la iteración 7.2 le diga que no: un rechazo por intento, sin saber nunca cuáles sí
    servían. La misma información, pero pidiéndola al revés.

    EL PERÍODO NO VIAJA EN LA PETICIÓN, sale del activo. Es la misma decisión que en el resto de
    la administración: un identificador de período copiado de otro semestre devolvería
    disponibilidad de un semestre que ya cerró, y el error solo se notaría al abrir el grupo.

    LA DISPONIBILIDAD SE MIDE CONTRA LA MISMA REGLA QUE LA IMPIDE. Un espacio está libre si
    ninguna franja suya se solapa con la pedida, con la misma comparación estricta que usa
    `SpaceConflictDetector` y el rango `[)` de la restricción de exclusión: una clase que termina
    a las 10:00 no ocupa las 10:00. Si esta consulta usara otro criterio, ofrecería aulas que
    `POST /admin/offerings` rechazaría a continuación, que es exactamente el tipo de
    contradicción que la Fase 6 se dedicó a eliminar.
    """

    def __init__(
        self,
        space_reader: SpaceReader,
        period_repository: PeriodRepository,
    ) -> None:
        self._spaces = space_reader
        self._periods = period_repository

    def execute(
        self,
        *,
        day_of_week: int,
        start_time: time,
        end_time: time,
        min_capacity: int | None = None,
        space_type: SpaceType | None = None,
    ) -> list[Space]:
        """Busca los espacios libres en esa franja.

        Args:
            day_of_week: día de la semana, de 1 (lunes) a 7 (domingo).
            start_time: hora de inicio de la franja que se quiere ocupar.
            end_time: hora de fin; tiene que ser posterior al inicio.
            min_capacity: si se indica, solo los que tengan sitio para esa cantidad. Los
                espacios de aforo DESCONOCIDO se incluyen igualmente, ver abajo.
            space_type: si se indica, solo los de ese tipo.

        Returns:
            Los espacios libres, ordenados por código.

        Raises:
            InvalidScheduleBlockError: si la franja pedida no es válida.
            NoActivePeriodError: si no hay ventana de matrícula activa. Sin período no hay
                semestre contra el que medir la ocupación.
        """
        self._verificar_franja(day_of_week=day_of_week, start_time=start_time, end_time=end_time)

        periodo = self._periods.find_active()

        if periodo is None:
            raise NoActivePeriodError()

        return self._spaces.find_available(
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
            enrollment_period_id=periodo.id,
            min_capacity=min_capacity,
            space_type=None if space_type is None else space_type.value,
        )

    @staticmethod
    def _verificar_franja(*, day_of_week: int, start_time: time, end_time: time) -> None:
        """Comprueba que la franja pedida tenga sentido antes de consultar nada.

        Se valida aquí y no solo en el schema porque la regla es del dominio: es la misma que
        `ScheduleBlock` aplica a cualquier franja, y una consulta de disponibilidad que aceptara
        «de 12 a 10» devolvería una lista vacía sin decir que la pregunta estaba mal.
        """
        if not 1 <= day_of_week <= 7:
            raise InvalidScheduleBlockError(
                f"El día '{day_of_week}' está fuera de rango (1 = lunes, 7 = domingo)"
            )

        if end_time <= start_time:
            raise InvalidScheduleBlockError(
                f"La hora de fin ({end_time}) debe ser posterior a la de inicio ({start_time})"
            )
