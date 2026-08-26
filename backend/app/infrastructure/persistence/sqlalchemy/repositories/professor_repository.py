"""Adaptador de `ProfessorReader` sobre SQLAlchemy."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.ports.repositories.professor_repository import ProfessorReader
from app.domain.entities.professor import Professor
from app.infrastructure.persistence.sqlalchemy.models.professor import ProfessorModel


class SQLAlchemyProfessorRepository(ProfessorReader):
    """Implementación del puerto de docentes contra PostgreSQL."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def exists(self, professor_id: UUID) -> bool:
        # `exists()` y no `get()`: la respuesta es la misma y no trae la fila entera para
        # descartarla, igual que en `CourseRepository.belongs_to_program`.
        sentencia = select(
            select(ProfessorModel.id).where(ProfessorModel.id == professor_id).exists()
        )
        return bool(self._session.execute(sentencia).scalar_one())

    def find_by_user_id(self, user_id: UUID) -> Professor | None:
        sentencia = select(ProfessorModel).where(ProfessorModel.user_id == user_id)
        modelo = self._session.execute(sentencia).scalar_one_or_none()

        if modelo is None:
            return None

        return Professor(
            id=modelo.id,
            full_name=modelo.full_name,
            email=modelo.email,
            user_id=modelo.user_id,
            created_at=modelo.created_at,
        )
