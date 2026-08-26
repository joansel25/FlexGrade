"""Adaptador de `SpaceRepository` sobre SQLAlchemy."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import time
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.application.ports.repositories.space_repository import SpaceRepository
from app.domain.entities.space import Space
from app.domain.value_objects.space_type import SpaceType
from app.infrastructure.persistence.sqlalchemy.models.schedule_block import ScheduleBlockModel
from app.infrastructure.persistence.sqlalchemy.models.space import SpaceModel


class SQLAlchemySpaceRepository(SpaceRepository):
    """Implementación del puerto de espacios contra PostgreSQL."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_id(self, space_id: UUID) -> Space | None:
        modelo = self._session.get(SpaceModel, space_id)
        return None if modelo is None else self._a_entidad(modelo)

    def find_by_code(self, code: str) -> Space | None:
        # Se normaliza el texto RECIBIDO y se compara contra la columna tal cual: los códigos se
        # guardan ya en mayúsculas y sin espacios —la migración 0009 los normalizó al crearlos—,
        # así que aplicar `UPPER` a la columna solo conseguiría que PostgreSQL no pudiera usar
        # el índice único de `code` y recorriera la tabla entera.
        sentencia = select(SpaceModel).where(SpaceModel.code == code.strip().upper())
        modelo = self._session.execute(sentencia).scalar_one_or_none()

        return None if modelo is None else self._a_entidad(modelo)

    def find_by_ids(self, space_ids: Sequence[UUID]) -> dict[UUID, Space]:
        if not space_ids:
            return {}

        sentencia = select(SpaceModel).where(SpaceModel.id.in_(space_ids))

        return {m.id: self._a_entidad(m) for m in self._session.execute(sentencia).scalars()}

    def find_available(
        self,
        *,
        day_of_week: int,
        start_time: time,
        end_time: time,
        enrollment_period_id: UUID,
        min_capacity: int | None = None,
        space_type: str | None = None,
    ) -> list[Space]:
        # `NOT EXISTS` y no un `LEFT JOIN ... IS NULL`: PostgreSQL corta en cuanto encuentra la
        # primera franja que estorba, en vez de materializar todos los cruces para descartarlos
        # después. La subconsulta la resuelve `ix_schedule_space`, que la 7.1 creó sobre
        # `(space_id, day_of_week)` justo para esta pregunta.
        ocupado = (
            select(ScheduleBlockModel.id)
            .where(ScheduleBlockModel.space_id == SpaceModel.id)
            .where(ScheduleBlockModel.enrollment_period_id == enrollment_period_id)
            .where(ScheduleBlockModel.day_of_week == day_of_week)
            # Solapamiento ESTRICTO, igual que `ScheduleBlock.overlaps` y que el rango `[)` de la
            # restricción de exclusión: terminar a las 10:00 y empezar a las 10:00 no es chocar.
            .where(ScheduleBlockModel.start_time < end_time)
            .where(start_time < ScheduleBlockModel.end_time)
            .exists()
        )

        sentencia = select(SpaceModel).where(~ocupado).order_by(SpaceModel.code)

        if space_type is not None:
            sentencia = sentencia.where(SpaceModel.space_type == space_type)

        if min_capacity is not None:
            # `IS NULL OR >=`: el aforo desconocido no descarta el aula. Ver el puerto.
            sentencia = sentencia.where(
                or_(SpaceModel.capacity.is_(None), SpaceModel.capacity >= min_capacity)
            )

        return [self._a_entidad(m) for m in self._session.execute(sentencia).scalars()]

    def search(self, *, space_type: str | None = None, campus: str | None = None) -> list[Space]:
        sentencia = select(SpaceModel).order_by(SpaceModel.code)

        if space_type is not None:
            sentencia = sentencia.where(SpaceModel.space_type == space_type)

        if campus is not None:
            # La sede sí se compara sin distinguir mayúsculas: es texto que escribe una persona
            # y no una clave normalizada como el código.
            sentencia = sentencia.where(func.upper(SpaceModel.campus) == campus.strip().upper())

        return [self._a_entidad(m) for m in self._session.execute(sentencia).scalars()]

    def save(self, space: Space) -> None:
        # `merge` y no `add`: sirve para uno nuevo y para uno que ya existe, que es lo que
        # promete el puerto.
        self._session.merge(
            SpaceModel(
                id=space.id,
                code=space.code,
                name=space.name,
                space_type=space.space_type.value,
                capacity=space.capacity,
                campus=space.campus,
                building=space.building,
            )
        )

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _a_entidad(modelo: SpaceModel) -> Space:
        """Convierte el modelo ORM en la entidad del dominio."""
        return Space(
            id=modelo.id,
            code=modelo.code,
            name=modelo.name,
            space_type=SpaceType(modelo.space_type),
            capacity=modelo.capacity,
            campus=modelo.campus,
            building=modelo.building,
            created_at=modelo.created_at,
        )
