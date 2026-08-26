"""DTOs de entrada de las operaciones de administración.

Casi todos los casos de uso reciben tipos del dominio o valores sueltos, y no hace falta más.
Este módulo existe para el caso contrario: cuando lo que llega de la petición **todavía no es**
un objeto del dominio y convertirlo exige consultar la base de datos.

Es lo que ocurre al abrir un grupo desde la iteración 7.1. La petición trae el CÓDIGO del aula
—`A-201`, que es lo que una persona escribe— y el value object `ScheduleBlock` lleva la entidad
`Space` ya resuelta. Traducir uno en otro es buscar el espacio y fallar si no existe, o sea una
decisión de negocio; hacerlo en el router lo convertiría en algo que decide, y los routers de
este proyecto no deciden (`CLAUDE.md`, «Nunca lógica de negocio en routers»).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True)
class ScheduleBlockRequest:
    """Una franja tal como llega en la petición, con el aula todavía sin resolver.

    Attributes:
        day_of_week: día de la semana, de 1 (lunes) a 7 (domingo).
        start_time: hora de inicio.
        end_time: hora de fin.
        space_code: código del espacio, o `None` para publicar la franja sin aula asignada.
            `None` es un valor legítimo y frecuente: el horario se publica antes de repartir
            los espacios.
    """

    day_of_week: int
    start_time: time
    end_time: time
    space_code: str | None = None
