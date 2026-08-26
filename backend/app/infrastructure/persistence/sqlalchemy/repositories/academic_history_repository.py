"""Adaptador de `AcademicHistoryReader` sobre SQLAlchemy."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.ports.repositories.academic_history_repository import AcademicHistoryReader
from app.domain.entities.academic_record import AcademicRecord
from app.domain.value_objects.grade import Grade
from app.domain.value_objects.history_status import HistoryStatus
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

    def find_recorded_courses(
        self, student_ids: Sequence[UUID], academic_period: str
    ) -> set[tuple[UUID, UUID]]:
        if not student_ids:
            return set()

        sentencia = (
            select(AcademicHistoryModel.student_id, AcademicHistoryModel.course_id)
            .where(AcademicHistoryModel.student_id.in_(student_ids))
            .where(AcademicHistoryModel.academic_period == academic_period)
        )

        return {(fila[0], fila[1]) for fila in self._session.execute(sentencia)}

    def save_all(self, records: Sequence[AcademicRecord]) -> None:
        if not records:
            return

        # `bulk_save_objects` y no `add` en un bucle: evita instanciar el estado de sesión de
        # cada objeto, que con miles de filas es la diferencia entre una transacción corta y
        # una que se queda abierta mientras la matrícula compite por las mismas tablas.
        self._session.bulk_save_objects(
            [
                AcademicHistoryModel(
                    id=registro.id,
                    student_id=registro.student_id,
                    course_id=registro.course_id,
                    academic_period=registro.academic_period,
                    final_grade=registro.final_grade.value,
                    status=registro.status.value,
                )
                for registro in records
            ]
        )

    def find_by_student(self, student_id: UUID) -> list[AcademicRecord]:
        sentencia = (
            select(AcademicHistoryModel).where(AcademicHistoryModel.student_id == student_id)
            # Descendente: lo último cursado es lo que se consulta. El orden lo pone la base y
            # no el caso de uso porque cae en el índice de la restricción UNIQUE, cuyo prefijo
            # es `student_id`.
            .order_by(
                AcademicHistoryModel.academic_period.desc(),
                AcademicHistoryModel.created_at,
            )
        )

        # `final_grade` es NOT NULL en la tabla —una fila del expediente sin nota no significa
        # nada—, pero el modelo la declara opcional. Se filtra en vez de asumir: si aparece una
        # sin nota es un dato roto, y pintarla como 0.0 diría que se reprobó.
        return [
            AcademicRecord(
                id=m.id,
                student_id=m.student_id,
                course_id=m.course_id,
                academic_period=m.academic_period,
                final_grade=Grade(m.final_grade),
                status=HistoryStatus(m.status),
                created_at=m.created_at,
            )
            for m in self._session.execute(sentencia).scalars()
            if m.final_grade is not None
        ]
