"""Dobles de prueba en memoria de los puertos de la aplicación.

Por el principio de sustitución de Liskov son intercambiables con los
adaptadores de SQLAlchemy: si un test pasa con estos y falla con aquellos, el
defecto está en el adaptador SQL, no en el contrato ni en la lógica de negocio.

Permiten probar los casos de uso en milisegundos y sin base de datos.
"""

from __future__ import annotations

from uuid import UUID

from app.application.dtos.auth_dto import TokenPayload, TokenType
from app.application.ports.auth_service import AuthService
from app.application.ports.repositories.student_repository import StudentRepository
from app.application.ports.repositories.user_repository import UserRepository
from app.domain.entities.student import Student
from app.domain.entities.user import User
from app.domain.exceptions.authentication import InvalidTokenError
from app.domain.value_objects.email import Email
from app.domain.value_objects.student_code import StudentCode
from app.domain.value_objects.user_role import UserRole


class InMemoryUserRepository(UserRepository):
    """Repositorio de usuarios respaldado por un diccionario."""

    def __init__(self, users: list[User] | None = None) -> None:
        self._users: dict[UUID, User] = {u.id: u for u in (users or [])}

    def find_by_id(self, user_id: UUID) -> User | None:
        return self._users.get(user_id)

    def find_by_email(self, email: Email) -> User | None:
        return next((u for u in self._users.values() if u.email == email), None)

    def save(self, user: User) -> None:
        self._users[user.id] = user


class InMemoryStudentRepository(StudentRepository):
    """Repositorio de estudiantes respaldado por un diccionario."""

    def __init__(self, students: list[Student] | None = None) -> None:
        self._students: dict[UUID, Student] = {s.id: s for s in (students or [])}

    def find_by_id(self, student_id: UUID) -> Student | None:
        return self._students.get(student_id)

    def find_by_user_id(self, user_id: UUID) -> Student | None:
        return next((s for s in self._students.values() if s.user_id == user_id), None)

    def find_by_student_code(self, student_code: StudentCode) -> Student | None:
        return next((s for s in self._students.values() if s.student_code == student_code), None)

    def save(self, student: Student) -> None:
        self._students[student.id] = student


class FakeAuthService(AuthService):
    """Servicio de autenticación determinista, sin criptografía real.

    El hash es un prefijo reconocible y el token una cadena estructurada. Los
    tests de los casos de uso comprueban ORQUESTACIÓN, no criptografía: esta
    última se verifica aparte, contra el adaptador real `JWTAuthService`.
    """

    ACCESS_EXPIRATION = 3600

    def __init__(self) -> None:
        self.tokens_emitidos: list[tuple[UUID, UserRole, TokenType]] = []

    def hash(self, plain_password: str) -> str:
        return f"hashed::{plain_password}"

    def verify(self, plain_password: str, password_hash: str) -> bool:
        return password_hash == f"hashed::{plain_password}"

    def create_token(self, user_id: UUID, role: UserRole, token_type: TokenType) -> str:
        self.tokens_emitidos.append((user_id, role, token_type))
        return f"{token_type.value}::{user_id}::{role.value}"

    def decode_token(self, token: str, expected_type: TokenType) -> TokenPayload:
        partes = token.split("::")
        if len(partes) != 3:
            raise InvalidTokenError("Token malformado")

        tipo, user_id, role = partes
        if tipo != expected_type.value:
            raise InvalidTokenError(f"Se esperaba un token '{expected_type.value}'")

        return TokenPayload(
            user_id=UUID(user_id),
            role=UserRole(role),
            token_type=expected_type,
        )

    def access_token_expiration_seconds(self) -> int:
        return self.ACCESS_EXPIRATION
