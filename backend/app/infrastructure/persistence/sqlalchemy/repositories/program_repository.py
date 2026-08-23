"""Adaptador de `ProgramRepository` sobre SQLAlchemy."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.ports.repositories.program_repository import ProgramRepository
from app.domain.entities.program import Program
from app.infrastructure.persistence.sqlalchemy.models.program import ProgramModel


class SQLAlchemyProgramRepository(ProgramRepository):
    """Implementación del puerto de programas contra PostgreSQL."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_id(self, program_id: UUID) -> Program | None:
        modelo = self._session.get(ProgramModel, program_id)
        return self._a_entidad(modelo) if modelo is not None else None

    def find_all(self) -> list[Program]:
        sentencia = select(ProgramModel).order_by(ProgramModel.code)
        return [self._a_entidad(m) for m in self._session.execute(sentencia).scalars()]

    @staticmethod
    def _a_entidad(modelo: ProgramModel) -> Program:
        """Convierte el modelo ORM en la entidad del dominio."""
        return Program(
            id=modelo.id,
            code=modelo.code,
            name=modelo.name,
            total_semesters=modelo.total_semesters,
            created_at=modelo.created_at,
        )
