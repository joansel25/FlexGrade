"""Dobles de prueba en memoria de los puertos de la aplicación.

Por el principio de sustitución de Liskov son intercambiables con los
adaptadores de SQLAlchemy: si un test pasa con estos y falla con aquellos, el
defecto está en el adaptador SQL, no en el contrato ni en la lógica de negocio.

Permiten probar los casos de uso en milisegundos y sin base de datos.
"""

from __future__ import annotations

from uuid import UUID

from app.application.dtos.auth_dto import TokenPayload, TokenType
from app.application.dtos.pagination import Page
from app.application.ports.auth_service import AuthService
from app.application.ports.repositories.course_repository import CourseRepository
from app.application.ports.repositories.offering_repository import OfferingRepository
from app.application.ports.repositories.period_repository import PeriodRepository
from app.application.ports.repositories.program_repository import ProgramRepository
from app.application.ports.repositories.student_repository import StudentRepository
from app.application.ports.repositories.user_repository import UserRepository
from app.domain.entities.course import Course
from app.domain.entities.course_offering import CourseOffering
from app.domain.entities.enrollment_period import EnrollmentPeriod
from app.domain.entities.program import Program
from app.domain.entities.student import Student
from app.domain.entities.user import User
from app.domain.exceptions.authentication import InvalidTokenError
from app.domain.value_objects.course_code import CourseCode
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


class InMemoryProgramRepository(ProgramRepository):
    """Repositorio de programas respaldado por un diccionario."""

    def __init__(self, programs: list[Program] | None = None) -> None:
        self._programs: dict[UUID, Program] = {p.id: p for p in (programs or [])}

    def find_by_id(self, program_id: UUID) -> Program | None:
        return self._programs.get(program_id)

    def find_all(self) -> list[Program]:
        return sorted(self._programs.values(), key=lambda p: p.code)


class InMemoryCourseRepository(CourseRepository):
    """Repositorio de materias respaldado por diccionarios.

    Reproduce el comportamiento observable del adaptador SQL, incluidos el orden por código y
    el filtrado por texto sin distinguir mayúsculas. Los filtros por programa y semestre se
    resuelven contra un plan de estudios declarado explícitamente en el constructor.
    """

    def __init__(
        self,
        courses: list[Course] | None = None,
        prerequisites: dict[UUID, list[Course]] | None = None,
        plan: dict[UUID, list[tuple[UUID, int]]] | None = None,
    ) -> None:
        """Construye el doble.

        Args:
            courses: las materias del catálogo.
            prerequisites: prerrequisitos directos, indexados por materia.
            plan: plan de estudios por programa, como pares `(course_id, semestre_sugerido)`.
        """
        self._courses: dict[UUID, Course] = {c.id: c for c in (courses or [])}
        self._prerequisites: dict[UUID, list[Course]] = prerequisites or {}
        self._plan: dict[UUID, list[tuple[UUID, int]]] = plan or {}

    def find_by_id(self, course_id: UUID) -> Course | None:
        return self._courses.get(course_id)

    def find_by_code(self, code: CourseCode) -> Course | None:
        return next((c for c in self._courses.values() if c.code == code), None)

    def find_prerequisites(self, course_id: UUID) -> list[Course]:
        return sorted(self._prerequisites.get(course_id, []), key=lambda c: c.code.value)

    def search(
        self,
        *,
        page: int,
        size: int,
        program_id: UUID | None = None,
        semester: int | None = None,
        search: str | None = None,
    ) -> Page[Course]:
        candidatas = list(self._courses.values())

        if program_id is not None:
            del_plan = {cid for cid, _ in self._plan.get(program_id, [])}
            candidatas = [c for c in candidatas if c.id in del_plan]

        if semester is not None:
            en_semestre = {
                cid for entradas in self._plan.values() for cid, sem in entradas if sem == semester
            }
            candidatas = [c for c in candidatas if c.id in en_semestre]

        if search and search.strip():
            texto = search.strip().lower()
            candidatas = [
                c for c in candidatas if texto in c.name.lower() or texto in c.code.value.lower()
            ]

        candidatas.sort(key=lambda c: c.code.value)
        desde = (page - 1) * size

        return Page(
            items=candidatas[desde : desde + size],
            total=len(candidatas),
            page=page,
            size=size,
        )


class InMemoryOfferingRepository(OfferingRepository):
    """Repositorio de grupos respaldado por un diccionario."""

    def __init__(self, offerings: list[CourseOffering] | None = None) -> None:
        self._offerings: dict[UUID, CourseOffering] = {o.id: o for o in (offerings or [])}

    def find_by_id(self, offering_id: UUID) -> CourseOffering | None:
        return self._offerings.get(offering_id)

    def find_by_course_and_period(
        self, course_id: UUID, enrollment_period_id: UUID
    ) -> list[CourseOffering]:
        return sorted(
            (
                o
                for o in self._offerings.values()
                if o.course_id == course_id and o.enrollment_period_id == enrollment_period_id
            ),
            key=lambda o: o.group_number,
        )

    def count_enrolled(self, offering_id: UUID) -> int | None:
        grupo = self._offerings.get(offering_id)
        return grupo.enrolled_count if grupo is not None else None


class InMemoryPeriodRepository(PeriodRepository):
    """Repositorio de períodos respaldado por un diccionario."""

    def __init__(self, periods: list[EnrollmentPeriod] | None = None) -> None:
        self._periods: dict[UUID, EnrollmentPeriod] = {p.id: p for p in (periods or [])}

    def find_active(self) -> EnrollmentPeriod | None:
        return next((p for p in self._periods.values() if p.is_active), None)

    def find_by_id(self, period_id: UUID) -> EnrollmentPeriod | None:
        return self._periods.get(period_id)
