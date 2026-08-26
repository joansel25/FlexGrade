"""Entidad Space: el aula, el laboratorio o el auditorio donde se dicta una clase."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.domain.value_objects.space_type import SpaceType


@dataclass
class Space:
    """Un espacio físico de la institución.

    ES UNA ENTIDAD Y NO UN TEXTO, y ese es todo el cambio de la iteración 7.1. Hasta ahora el
    aula era una cadena libre dentro de cada franja horaria: `schedule_blocks.classroom`. Con
    eso, «A-201», «A201» y «Aula A-201» eran tres aulas distintas para la base de datos y la
    misma para las personas, así que preguntar «¿qué hay en A-201 el martes?» no tenía respuesta
    fiable y **nada impedía reservar el mismo salón dos veces a la misma hora**. Un texto no
    puede estar ocupado; una fila sí.

    Attributes:
        id: identificador único del espacio.
        code: código institucional con el que se lo nombra (`A-201`). Es su clave natural: es lo
            que aparece en un horario impreso y lo que alguien escribe al asignar un aula, así
            que la API lo acepta en vez de exigir un UUID.
        name: nombre descriptivo, cuando lo tiene («Laboratorio de Redes»). Opcional: la mayoría
            de las aulas no se llaman de ninguna manera, solo se numeran.
        space_type: aula, laboratorio o auditorio.
        capacity: cuántas personas caben. **Puede ser desconocida**, y por eso admite `None`:
            los espacios que la migración `0009` creó a partir de los textos existentes no
            traían aforo de ninguna parte, e inventarles un número habría sido peor que admitir
            que no se sabe. La comprobación de aforo de la iteración 7.2 solo puede aplicarse
            donde el dato existe.
        campus: sede en la que está.
        building: bloque o edificio dentro de la sede.
        created_at: instante de creación del registro.
    """

    id: UUID
    code: str
    space_type: SpaceType
    name: str | None = None
    capacity: int | None = None
    campus: str | None = None
    building: str | None = None
    created_at: datetime | None = field(default=None)

    def fits(self, people: int) -> bool | None:
        """Indica si caben `people` personas en este espacio.

        Devuelve `None` cuando el aforo se desconoce, y no `True` ni `False`. Es deliberado:
        «no sé» no es «sí» ni «no», y colapsarlo en cualquiera de los dos convierte un dato
        ausente en una afirmación. Con `True` se aprobarían asignaciones que no caben; con
        `False` se bloquearían aulas perfectamente utilizables solo porque nadie ha medido su
        aforo todavía. Quien llama decide qué hacer con la incertidumbre.

        Args:
            people: cuántas personas tendrían que caber.

        Returns:
            `True` si caben, `False` si no, `None` si el aforo es desconocido.
        """
        if self.capacity is None:
            return None

        return people <= self.capacity

    def describe(self) -> str:
        """Devuelve cómo se nombra el espacio en un horario.

        El código solo, salvo que tenga nombre propio: «A-201» basta para encontrar un aula,
        mientras que «LAB-03 (Laboratorio de Redes)» ahorra el paso de preguntar cuál es.
        """
        return self.code if self.name is None else f"{self.code} ({self.name})"
