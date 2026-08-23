"""Constructores de entidades de prueba.

Centralizan los valores por defecto para que el bloque *arrange* de cada test
mencione solo lo que ese test necesita, y no una lista de campos irrelevantes.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

from app.domain.entities.student import Student
from app.domain.entities.user import User
from app.domain.value_objects.email import Email
from app.domain.value_objects.student_code import StudentCode
from app.domain.value_objects.user_role import UserRole

PASSWORD_POR_DEFECTO = "SecurePass123"


def crear_usuario(
    *,
    user_id: UUID | None = None,
    email: str = "estudiante@tdea.edu.co",
    password: str = PASSWORD_POR_DEFECTO,
    role: UserRole = UserRole.STUDENT,
    is_active: bool = True,
) -> User:
    """Construye un `User` cuyo hash coincide con el de `FakeAuthService`."""
    return User(
        id=user_id or uuid4(),
        email=Email(email),
        password_hash=f"hashed::{password}",
        role=role,
        is_active=is_active,
    )


def crear_estudiante(
    *,
    student_id: UUID | None = None,
    user_id: UUID | None = None,
    student_code: str = "1234567",
    program_id: UUID | None = None,
    current_semester: int = 6,
    full_name: str = "Joan Sebastián Cárdenas",
) -> Student:
    """Construye un `Student` con datos académicos verosímiles."""
    return Student(
        id=student_id or uuid4(),
        user_id=user_id or uuid4(),
        student_code=StudentCode(student_code),
        program_id=program_id or uuid4(),
        current_semester=current_semester,
        full_name=full_name,
        enrollment_date=date(2022, 1, 15),
    )
