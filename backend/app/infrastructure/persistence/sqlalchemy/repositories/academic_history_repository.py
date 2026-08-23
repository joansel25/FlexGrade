"""Adaptador de `AcademicHistoryReader` sobre SQLAlchemy."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.ports.repositories.academic_history_repository import AcademicHistoryReader
from app.infrastructure.persistence.sqlalchemy.models.academic_history import AcademicHistoryModel


class SQLAlchemyAcademicHistoryRepository(AcademicHistoryReader):
    """Implementación del puerto del historial académico contra PostgreSQL."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_approved_course_ids(self, student_id: UUID) -> set[UUID]:
        # Se selecciona solo la columna que hace falta, no la fila entera: de este historial
        # únicamente interesa QUÉ aprobó, no con qué nota ni en qué semestre. La consulta cae
        # de lleno en el índice `ix_history_student_status`.
        sentencia = (
            select(AcademicHistoryModel.course_id)
            .where(AcademicHistoryModel.student_id == student_id)
            .where(AcademicHistoryModel.status == "APPROVED")
        )
        return set(self._session.execute(sentencia).scalars())
