"""Contenedor de resultados paginados, compartido por las consultas de listado.

`API.md` fija un único formato de respuesta paginada —`items`, `total`, `page`, `size`— para
todos los listados. Este DTO es su equivalente en la capa de aplicación: los repositorios lo
devuelven y los routers lo traducen al schema Pydantic sin volver a calcular nada.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")

# Techo del tamaño de página. Sin él, `?size=100000` convierte un endpoint de catálogo en una
# forma trivial de tumbar la base de datos durante el pico de matrícula.
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


@dataclass(frozen=True)
class Page(Generic[T]):
    """Una página de resultados junto con el total de coincidencias.

    Attributes:
        items: los elementos de esta página.
        total: cuántos elementos hay en total, no solo en esta página. Es lo que permite al
            frontend saber cuántas páginas existen.
        page: número de página, empezando en 1.
        size: tamaño de página solicitado.
    """

    items: Sequence[T]
    total: int
    page: int
    size: int
