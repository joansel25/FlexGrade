"""Casos de uso: alta y consulta del inventario de espacios físicos."""

from __future__ import annotations

from uuid import uuid4

from app.application.ports.repositories.space_repository import SpaceReader, SpaceRepository
from app.application.ports.unit_of_work import UnitOfWork
from app.domain.entities.space import Space
from app.domain.exceptions.admin import DuplicateSpaceCodeError
from app.domain.value_objects.space_type import SpaceType


class CreateSpaceUseCase:
    """Da de alta un espacio físico.

    Hasta ahora el inventario solo se poblaba con el seed o a mano contra la base. Sin esto, la
    iteración 7.1 dejó los espacios como entidad y nadie podía crear uno: asignar un aula nueva
    exigía un `INSERT` escrito por alguien con acceso a PostgreSQL.

    EL CÓDIGO SE NORMALIZA ANTES DE COMPROBAR SI EXISTE, igual que hace `CourseCode` con las
    materias. Sin eso, `a-201` y `A-201` convivirían como dos aulas distintas y el problema que
    la 7.1 vino a resolver volvería por la puerta de atrás: dos filas para el mismo salón, y una
    restricción de doble reserva que no puede impedir nada porque cree que son sitios distintos.
    """

    def __init__(self, space_repository: SpaceRepository, unit_of_work: UnitOfWork) -> None:
        self._spaces = space_repository
        self._uow = unit_of_work

    def execute(
        self,
        *,
        code: str,
        space_type: SpaceType,
        name: str | None = None,
        capacity: int | None = None,
        campus: str | None = None,
        building: str | None = None,
    ) -> Space:
        """Crea el espacio.

        Args:
            code: código institucional. Se guarda normalizado, en mayúsculas y sin espacios.
            space_type: aula, laboratorio o auditorio.
            name: nombre descriptivo, si lo tiene.
            capacity: aforo. Puede quedar sin saber; ver `Space`.
            campus: sede.
            building: bloque o edificio.

        Returns:
            El espacio creado.

        Raises:
            DuplicateSpaceCodeError: si ya existe uno con ese código.
        """
        normalizado = code.strip().upper()

        with self._uow:
            if self._spaces.find_by_code(normalizado) is not None:
                # La restricción `UNIQUE` de la tabla lo impediría igual, pero devolvería un
                # error de integridad y un 500. Comprobarlo aquí produce un mensaje que dice
                # qué código está repetido.
                raise DuplicateSpaceCodeError(normalizado)

            espacio = Space(
                id=uuid4(),
                code=normalizado,
                space_type=space_type,
                name=name,
                capacity=capacity,
                campus=campus,
                building=building,
            )

            self._spaces.save(espacio)
            self._uow.commit()

        return espacio


class ListSpacesUseCase:
    """Devuelve el inventario de espacios, con filtros opcionales.

    Sin paginar, al contrario que el catálogo de materias: una institución tiene decenas o pocos
    cientos de espacios, no miles, y quien va a asignar un aula necesita verlos todos para
    elegir. La razón está escrita en el puerto.
    """

    def __init__(self, space_reader: SpaceReader) -> None:
        self._spaces = space_reader

    def execute(
        self, *, space_type: SpaceType | None = None, campus: str | None = None
    ) -> list[Space]:
        """Lista el inventario.

        Args:
            space_type: si se indica, solo los de ese tipo.
            campus: si se indica, solo los de esa sede.

        Returns:
            Los espacios que cumplen los filtros, ordenados por código.
        """
        return self._spaces.search(
            space_type=None if space_type is None else space_type.value, campus=campus
        )
