"""Adaptador de `StudentRepository` sobre SQLAlchemy."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.ports.repositories.student_repository import StudentRepository
from app.domain.entities.student import Student
from app.domain.value_objects.student_code import StudentCode
from app.infrastructure.persistence.sqlalchemy.models.student import StudentModel


class SQLAlchemyStudentRepository(StudentRepository):
    """Implementación del puerto de estudiantes contra PostgreSQL."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_id(self, student_id: UUID) -> Student | None:
        modelo = self._session.get(StudentModel, student_id)
        return self._a_entidad(modelo) if modelo is not None else None

    def find_by_user_id(self, user_id: UUID) -> Student | None:
        # `user_id` tiene restricción UNIQUE, así que devuelve como mucho una fila
        # y su índice ya está creado por esa restricción.
        sentencia = select(StudentModel).where(StudentModel.user_id == user_id)
        modelo = self._session.execute(sentencia).scalar_one_or_none()
        return self._a_entidad(modelo) if modelo is not None else None

    def find_by_ids(self, student_ids: Sequence[UUID]) -> list[Student]:
        if not student_ids:
            # `IN ()` no es SQL válido, y aunque lo fuera sería un viaje a la base para no
            # preguntar nada.
            return []

        sentencia = select(StudentModel).where(StudentModel.id.in_(student_ids))

        return [self._a_entidad(m) for m in self._session.execute(sentencia).scalars()]

    def find_by_student_code(self, student_code: StudentCode) -> Student | None:
        sentencia = select(StudentModel).where(StudentModel.student_code == student_code.value)
        modelo = self._session.execute(sentencia).scalar_one_or_none()
        return self._a_entidad(modelo) if modelo is not None else None

    def save(self, student: Student) -> None:
        modelo = self._session.get(StudentModel, student.id)

        if modelo is None:
            self._session.add(self._a_modelo(student))
            return

        modelo.student_code = student.student_code.value
        modelo.program_id = student.program_id
        modelo.current_semester = student.current_semester
        modelo.full_name = student.full_name
        modelo.enrollment_date = student.enrollment_date

    @staticmethod
    def _a_entidad(modelo: StudentModel) -> Student:
        """Convierte el modelo ORM en la entidad del dominio."""
        return Student(
            id=modelo.id,
            user_id=modelo.user_id,
            student_code=StudentCode(modelo.student_code),
            program_id=modelo.program_id,
            current_semester=modelo.current_semester,
            full_name=modelo.full_name,
            enrollment_date=modelo.enrollment_date,
            created_at=modelo.created_at,
        )

    @staticmethod
    def _a_modelo(student: Student) -> StudentModel:
        """Convierte la entidad del dominio en el modelo ORM."""
        return StudentModel(
            id=student.id,
            user_id=student.user_id,
            student_code=student.student_code.value,
            program_id=student.program_id,
            current_semester=student.current_semester,
            full_name=student.full_name,
            enrollment_date=student.enrollment_date,
        )
