"""Dobles de prueba en memoria de los puertos de la aplicación.

Por el principio de sustitución de Liskov son intercambiables con los
adaptadores de SQLAlchemy: si un test pasa con estos y falla con aquellos, el
defecto está en el adaptador SQL, no en el contrato ni en la lógica de negocio.

Permiten probar los casos de uso en milisegundos y sin base de datos.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import time
from uuid import UUID

from app.application.dtos.auth_dto import TokenPayload, TokenType
from app.application.dtos.pagination import Page
from app.application.dtos.report_dto import (
    OfferingOccupancyDTO,
    ProgramEnrollmentsDTO,
    ReportTotalsDTO,
)
from app.application.ports.auth_service import AuthService
from app.application.ports.cache_service import CacheService
from app.application.ports.repositories.academic_history_repository import AcademicHistoryReader
from app.application.ports.repositories.course_repository import CourseRepository
from app.application.ports.repositories.enrollment_repository import EnrollmentRepository
from app.application.ports.repositories.offering_repository import OfferingRepository
from app.application.ports.repositories.period_repository import PeriodRepository
from app.application.ports.repositories.professor_repository import ProfessorReader
from app.application.ports.repositories.program_repository import ProgramRepository
from app.application.ports.repositories.report_repository import ReportReader
from app.application.ports.repositories.space_repository import SpaceRepository
from app.application.ports.repositories.student_repository import StudentRepository
from app.application.ports.repositories.user_repository import UserRepository
from app.application.ports.unit_of_work import UnitOfWork
from app.domain.entities.course import Course
from app.domain.entities.course_offering import CourseOffering
from app.domain.entities.course_requirement import CourseRequirement
from app.domain.entities.enrollment import Enrollment
from app.domain.entities.enrollment_period import EnrollmentPeriod
from app.domain.entities.program import Program
from app.domain.entities.space import Space
from app.domain.entities.student import Student
from app.domain.entities.user import User
from app.domain.exceptions.authentication import InvalidTokenError
from app.domain.services.space_conflict_detector import SpaceReservation
from app.domain.value_objects.course_code import CourseCode
from app.domain.value_objects.email import Email
from app.domain.value_objects.enrollment_status import EnrollmentStatus
from app.domain.value_objects.requirement_type import RequirementType
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
        corequisites: dict[UUID, list[Course]] | None = None,
    ) -> None:
        """Construye el doble.

        Args:
            courses: las materias del catálogo.
            prerequisites: prerrequisitos directos, indexados por materia.
            plan: plan de estudios por programa, como pares `(course_id, semestre_sugerido)`.
            corequisites: correquisitos directos, indexados por materia.

        Los requisitos se declaran SIN programa, al contrario que en el adaptador real. Es
        deliberado: casi ningún test unitario va sobre la diferencia entre planes, y obligarles
        a declarar un programa para cada requisito llenaría de ruido su preparación. El test
        que sí necesita comprobar que los requisitos cambian según la carrera es de integración
        y corre contra PostgreSQL, donde la clave foránea compuesta lo impone de verdad.
        """
        self._courses: dict[UUID, Course] = {c.id: c for c in (courses or [])}
        self._prerequisites: dict[UUID, list[Course]] = prerequisites or {}
        self._plan: dict[UUID, list[tuple[UUID, int]]] = plan or {}
        self._corequisites: dict[UUID, list[Course]] = corequisites or {}

    def find_by_id(self, course_id: UUID) -> Course | None:
        return self._courses.get(course_id)

    def find_by_code(self, code: CourseCode) -> Course | None:
        return next((c for c in self._courses.values() if c.code == code), None)

    def find_by_ids(self, course_ids: Sequence[UUID]) -> dict[UUID, Course]:
        return {cid: self._courses[cid] for cid in course_ids if cid in self._courses}

    def find_requirements(self, course_id: UUID, program_id: UUID) -> list[CourseRequirement]:
        requisitos = [
            CourseRequirement(course=c, requirement_type=RequirementType.PREREQUISITE)
            for c in self._prerequisites.get(course_id, [])
        ] + [
            CourseRequirement(course=c, requirement_type=RequirementType.COREQUISITE)
            for c in self._corequisites.get(course_id, [])
        ]

        return sorted(requisitos, key=lambda r: r.course.code.value)

    def find_requirements_for_courses(
        self, course_ids: Sequence[UUID], program_id: UUID
    ) -> dict[UUID, list[CourseRequirement]]:
        """Reproduce el contrato del adaptador: las materias sin requisitos NO son clave."""
        por_materia = {
            course_id: self.find_requirements(course_id, program_id) for course_id in course_ids
        }

        return {cid: requisitos for cid, requisitos in por_materia.items() if requisitos}

    def find_corequisite_dependents(self, course_id: UUID, program_id: UUID) -> list[Course]:
        """Recorre las declaraciones al revés en vez de pedir una tabla inversa.

        Deducirlo de `corequisites` y no declararlo aparte evita el fallo más probable de un
        doble: que el test declare `A -> B` en un sitio y se olvide de reflejarlo en el otro, y
        acabe probando una regla que la base de datos nunca aplicaría.
        """
        dependientes = [
            self._courses[dependiente_id]
            for dependiente_id, exigidas in self._corequisites.items()
            if any(c.id == course_id for c in exigidas) and dependiente_id in self._courses
        ]

        return sorted(dependientes, key=lambda c: c.code.value)

    def find_mutual_corequisites(self, course_id: UUID, program_id: UUID) -> set[UUID]:
        """Calcula la reciprocidad en vez de declararla.

        Deducirla de `corequisites` y no pedirla como un tercer parámetro evita el fallo más
        probable de un doble: que el test declare `A <-> B` en un sitio y se olvide de la
        vuelta en el otro, y acabe probando una regla que la base de datos nunca aplicaría.
        """
        mios = {c.id for c in self._corequisites.get(course_id, [])}

        return {
            otro for otro in mios if course_id in {c.id for c in self._corequisites.get(otro, [])}
        }

    def belongs_to_program(self, course_id: UUID, program_id: UUID) -> bool:
        # Si no se declaro plan de estudios, se acepta todo: la mayoria de los tests no van
        # sobre esta regla y obligarles a declararlo seria ruido en su bloque de preparacion.
        if not self._plan:
            return True

        return any(cid == course_id for cid, _ in self._plan.get(program_id, []))

    def find_study_plan(self, program_id: UUID) -> list[tuple[Course, int, bool]]:
        """Reproduce el orden del adaptador SQL: por semestre y luego por código."""
        entradas = [
            (self._courses[cid], semestre, True)
            for cid, semestre in self._plan.get(program_id, [])
            if cid in self._courses
        ]

        return sorted(entradas, key=lambda e: (e[1], e[0].code.value))

    def find_requirement_dependents(self, course_id: UUID, program_id: UUID) -> list[Course]:
        """Quién exige esta materia, de CUALQUIER tipo.

        Se deduce de `prerequisites` y `corequisites` juntos, al contrario que
        `find_corequisite_dependents`, que solo mira los segundos.
        """
        dependientes = [
            self._courses[dependiente_id]
            for tabla in (self._prerequisites, self._corequisites)
            for dependiente_id, exigidas in tabla.items()
            if any(c.id == course_id for c in exigidas) and dependiente_id in self._courses
        ]

        return sorted({d.id: d for d in dependientes}.values(), key=lambda c: c.code.value)

    def save_plan_entry(
        self,
        *,
        program_id: UUID,
        course_id: UUID,
        suggested_semester: int,
        is_mandatory: bool,
    ) -> None:
        entradas = [e for e in self._plan.get(program_id, []) if e[0] != course_id]
        entradas.append((course_id, suggested_semester))
        self._plan[program_id] = entradas

    def remove_plan_entry(self, *, program_id: UUID, course_id: UUID) -> bool:
        entradas = self._plan.get(program_id, [])
        quedan = [e for e in entradas if e[0] != course_id]

        if len(quedan) == len(entradas):
            return False

        self._plan[program_id] = quedan
        return True

    def save(self, course: Course) -> None:
        self._courses[course.id] = course

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
    """Repositorio de grupos respaldado por un diccionario.

    Las lecturas devuelven una COPIA, igual que hace el adaptador SQL: `_a_entidad` construye
    una entidad nueva en cada consulta, asi que mutarla no toca la base de datos. Devolver el
    objeto almacenado haria que este doble se comportara distinto del adaptador real —una
    mutacion del dominio se persistiria sola— y por el principio de sustitucion de Liskov
    deben ser intercambiables.
    """

    def __init__(self, offerings: list[CourseOffering] | None = None) -> None:
        self._offerings: dict[UUID, CourseOffering] = {o.id: o for o in (offerings or [])}

    @staticmethod
    def _copia(offering: CourseOffering) -> CourseOffering:
        return replace(offering)

    def find_by_id(self, offering_id: UUID) -> CourseOffering | None:
        guardado = self._offerings.get(offering_id)
        return self._copia(guardado) if guardado is not None else None

    def find_by_course_and_period(
        self, course_id: UUID, enrollment_period_id: UUID
    ) -> list[CourseOffering]:
        return [
            self._copia(o)
            for o in sorted(
                (
                    o
                    for o in self._offerings.values()
                    if o.course_id == course_id and o.enrollment_period_id == enrollment_period_id
                ),
                key=lambda o: o.group_number,
            )
        ]

    def find_space_reservations(
        self, space_ids: Sequence[UUID], enrollment_period_id: UUID
    ) -> list[SpaceReservation]:
        """Reproduce la consulta de ocupación sobre los grupos guardados.

        El código de la materia no está en `CourseOffering` —solo su identificador—, así que el
        doble devuelve una cadena vacía. Es suficiente: lo que los tests comprueban es QUÉ
        franja choca y con qué grupo, no cómo se llama la materia, y eso lo cubre el test de
        integración contra el `SELECT` real.
        """
        pedidos = set(space_ids)

        return [
            SpaceReservation(
                space_id=franja.space.id,
                block=franja,
                course_code="",
                group_number=o.group_number,
            )
            for o in self._offerings.values()
            if o.enrollment_period_id == enrollment_period_id
            for franja in o.schedule
            if franja.space is not None and franja.space.id in pedidos
        ]

    def find_course_ids_offered_in(
        self, course_ids: Sequence[UUID], enrollment_period_id: UUID
    ) -> set[UUID]:
        pedidas = set(course_ids)

        return {
            o.course_id
            for o in self._offerings.values()
            if o.enrollment_period_id == enrollment_period_id and o.course_id in pedidas
        }

    def find_by_ids(self, offering_ids: Sequence[UUID]) -> list[CourseOffering]:
        return [
            self._copia(o)
            for o in sorted(
                (self._offerings[oid] for oid in offering_ids if oid in self._offerings),
                key=lambda o: o.group_number,
            )
        ]

    def count_enrolled(self, offering_id: UUID) -> int | None:
        grupo = self._offerings.get(offering_id)
        return grupo.enrolled_count if grupo is not None else None

    def try_reserve_slot(self, offering_id: UUID) -> bool:
        """Reproduce el UPDATE condicionado del adaptador SQL.

        En memoria no hay concurrencia real, asi que esto solo reproduce el COMPORTAMIENTO
        observable: descuenta si queda sitio y devuelve `False` si no. Que sea atomico bajo
        contencion es cosa de PostgreSQL, y se verifica con hilos reales en
        `test_enrollment_concurrency.py`.
        """
        grupo = self._offerings.get(offering_id)

        if grupo is None or grupo.enrolled_count >= grupo.total_capacity:
            return False

        grupo.enrolled_count += 1
        grupo.version += 1
        return True

    def try_release_slot(self, offering_id: UUID) -> bool:
        grupo = self._offerings.get(offering_id)

        if grupo is None or grupo.enrolled_count <= 0:
            return False

        grupo.enrolled_count -= 1
        grupo.version += 1
        return True

    def save(self, offering: CourseOffering) -> None:
        # Se guarda una copia por la misma razon que las lecturas devuelven una: quien llama
        # conserva su entidad y mutarla despues no debe cambiar lo "persistido".
        self._offerings[offering.id] = self._copia(offering)

    def update_capacity(
        self, offering_id: UUID, *, new_capacity: int, expected_version: int
    ) -> bool:
        """Reproduce el UPDATE condicionado por version del adaptador SQL."""
        grupo = self._offerings.get(offering_id)

        if grupo is None or grupo.version != expected_version:
            return False

        # Misma guarda que el SQL: el cupo nunca queda por debajo de la ocupacion real.
        if new_capacity < grupo.enrolled_count:
            return False

        grupo.total_capacity = new_capacity
        grupo.version += 1
        return True

    def mover_version(self, offering_id: UUID) -> None:
        """Incrementa la version del grupo, para simular que otra escritura se adelanto."""
        self._offerings[offering_id].version += 1

    def llenar(self, offering_id: UUID) -> None:
        """Deja el grupo sin cupos, para simular que se lleno tras leerlo."""
        grupo = self._offerings[offering_id]
        grupo.enrolled_count = grupo.total_capacity


class InMemoryPeriodRepository(PeriodRepository):
    """Repositorio de períodos respaldado por un diccionario."""

    def __init__(self, periods: list[EnrollmentPeriod] | None = None) -> None:
        self._periods: dict[UUID, EnrollmentPeriod] = {p.id: p for p in (periods or [])}

    def find_active(self) -> EnrollmentPeriod | None:
        return next((p for p in self._periods.values() if p.is_active), None)

    def find_by_id(self, period_id: UUID) -> EnrollmentPeriod | None:
        return self._periods.get(period_id)

    def find_by_code(self, code: str) -> EnrollmentPeriod | None:
        return next((p for p in self._periods.values() if p.code == code), None)

    def list_all(self, *, page: int, size: int) -> Page[EnrollmentPeriod]:
        # Mismo orden que el adaptador SQL: de la mas reciente a la mas antigua.
        ordenados = sorted(self._periods.values(), key=lambda p: p.starts_at, reverse=True)
        desde = (page - 1) * size

        return Page(
            items=ordenados[desde : desde + size],
            total=len(ordenados),
            page=page,
            size=size,
        )

    def save(self, period: EnrollmentPeriod) -> None:
        self._periods[period.id] = period


class InMemorySpaceRepository(SpaceRepository):
    """Inventario de espacios en memoria, indexado por código además de por identificador.

    Reproduce la normalización del adaptador SQL —`strip()` y mayúsculas al buscar por código—
    porque es comportamiento observable: un test que pase `a-201 ` tiene que encontrar el mismo
    espacio que uno que pase `A-201`, o el doble y el adaptador dejarían de ser
    intercambiables.
    """

    def __init__(self, spaces: list[Space] | None = None) -> None:
        self._spaces: dict[UUID, Space] = {s.id: s for s in (spaces or [])}

    def find_by_id(self, space_id: UUID) -> Space | None:
        return self._spaces.get(space_id)

    def find_by_code(self, code: str) -> Space | None:
        normalizado = code.strip().upper()

        return next((s for s in self._spaces.values() if s.code == normalizado), None)

    def find_by_ids(self, space_ids: Sequence[UUID]) -> dict[UUID, Space]:
        return {sid: self._spaces[sid] for sid in space_ids if sid in self._spaces}

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
        """Filtra el inventario por tipo y aforo, sin ocupación.

        El doble NO conoce las franjas reservadas: vive en el repositorio de espacios y las
        franjas viven en el de grupos. Lo que se comprueba con él es que el caso de uso valide
        la franja y resuelva el período; que la ocupación se calcule bien es cosa del `SELECT`
        real, y eso se prueba contra PostgreSQL.

        Sí reproduce la regla del aforo desconocido, que es una decisión de diseño y no un
        detalle del SQL: `capacity is None` no descarta el espacio.
        """
        libres = [
            s
            for s in self._spaces.values()
            if (space_type is None or s.space_type.value == space_type)
            and (min_capacity is None or s.capacity is None or s.capacity >= min_capacity)
        ]

        return sorted(libres, key=lambda s: s.code)

    def search(self, *, space_type: str | None = None, campus: str | None = None) -> list[Space]:
        encontrados = [
            s
            for s in self._spaces.values()
            if (space_type is None or s.space_type.value == space_type)
            and (campus is None or (s.campus or "").upper() == campus.strip().upper())
        ]

        return sorted(encontrados, key=lambda s: s.code)

    def save(self, space: Space) -> None:
        self._spaces[space.id] = space


class InMemoryProfessorReader(ProfessorReader):
    """Lector de docentes respaldado por un conjunto de identificadores."""

    def __init__(self, professor_ids: set[UUID] | None = None) -> None:
        self._ids = professor_ids or set()

    def exists(self, professor_id: UUID) -> bool:
        return professor_id in self._ids


class FakeReportReader(ReportReader):
    """Reportes de mentira, con las cifras que el test declare.

    Los casos de uso de reporte no calculan nada: eligen el periodo, sellan la hora y componen
    la respuesta. Lo que se prueba aqui es esa ORQUESTACION; que los `GROUP BY` cuenten bien se
    verifica contra PostgreSQL, que es quien los ejecuta.
    """

    def __init__(
        self,
        totals: ReportTotalsDTO | None = None,
        by_program: list[ProgramEnrollmentsDTO] | None = None,
        occupancy: list[OfferingOccupancyDTO] | None = None,
    ) -> None:
        self._totals = totals or ReportTotalsDTO(
            total_enrollments=0, unique_students=0, active_offerings=0
        )
        self._by_program = by_program or []
        self._occupancy = occupancy or []
        self.periodos_consultados: list[UUID] = []

    def enrollment_totals(self, enrollment_period_id: UUID) -> ReportTotalsDTO:
        self.periodos_consultados.append(enrollment_period_id)
        return self._totals

    def enrollments_by_program(self, enrollment_period_id: UUID) -> list[ProgramEnrollmentsDTO]:
        self.periodos_consultados.append(enrollment_period_id)
        return list(self._by_program)

    def offering_occupancy(
        self, enrollment_period_id: UUID, *, page: int, size: int
    ) -> Page[OfferingOccupancyDTO]:
        self.periodos_consultados.append(enrollment_period_id)
        desde = (page - 1) * size

        return Page(
            items=self._occupancy[desde : desde + size],
            total=len(self._occupancy),
            page=page,
            size=size,
        )


class InMemoryCacheService(CacheService):
    """Caché en memoria que registra cuántas veces se la consulta.

    Los contadores permiten afirmar en un test que la segunda llamada NO fue a la base de
    datos, que es justamente lo que un test de caché debe demostrar: sin ellos solo se
    comprobaría que el resultado es el mismo, cosa que también ocurriría sin caché alguna.
    """

    def __init__(self) -> None:
        self._datos: dict[str, str] = {}
        self.lecturas = 0
        self.escrituras = 0
        self.invalidaciones = 0

    def get(self, key: str) -> str | None:
        self.lecturas += 1
        return self._datos.get(key)

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self.escrituras += 1
        self._datos[key] = value

    def delete(self, key: str) -> None:
        self.invalidaciones += 1
        self._datos.pop(key, None)

    def envenenar(self, key: str, contenido: str) -> None:
        """Coloca contenido corrupto bajo una clave, saltándose el contador de escrituras."""
        self._datos[key] = contenido

    def contiene(self, key: str) -> bool:
        return key in self._datos


class CacheCaida(CacheService):
    """Caché que falla en toda operación, como un Redis caído.

    El adaptador real captura `RedisError` y degrada; este doble simula la capa que hay por
    debajo de esa captura para comprobar que, aun así, los casos de uso responden.
    """

    def get(self, key: str) -> str | None:
        return None

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        return None

    def delete(self, key: str) -> None:
        return None


class ContadorDeConsultas(OfferingRepository):
    """Envoltorio que cuenta las llamadas a un repositorio de grupos.

    Comprueba la regla que sostiene todo el diseño de la caché de este endpoint:
    `count_enrolled` tiene que ejecutarse SIEMPRE, incluso cuando el grupo viene de la caché.
    """

    def __init__(self, interno: OfferingRepository) -> None:
        self._interno = interno
        self.llamadas_find_by_id = 0
        self.llamadas_count_enrolled = 0

    def find_by_id(self, offering_id: UUID) -> CourseOffering | None:
        self.llamadas_find_by_id += 1
        return self._interno.find_by_id(offering_id)

    def find_by_course_and_period(
        self, course_id: UUID, enrollment_period_id: UUID
    ) -> list[CourseOffering]:
        return self._interno.find_by_course_and_period(course_id, enrollment_period_id)

    def count_enrolled(self, offering_id: UUID) -> int | None:
        self.llamadas_count_enrolled += 1
        return self._interno.count_enrolled(offering_id)

    def find_by_ids(self, offering_ids: Sequence[UUID]) -> list[CourseOffering]:
        return self._interno.find_by_ids(offering_ids)

    def find_course_ids_offered_in(
        self, course_ids: Sequence[UUID], enrollment_period_id: UUID
    ) -> set[UUID]:
        return self._interno.find_course_ids_offered_in(course_ids, enrollment_period_id)

    def find_space_reservations(
        self, space_ids: Sequence[UUID], enrollment_period_id: UUID
    ) -> list[SpaceReservation]:
        return self._interno.find_space_reservations(space_ids, enrollment_period_id)

    def try_reserve_slot(self, offering_id: UUID) -> bool:
        return self._interno.try_reserve_slot(offering_id)

    def try_release_slot(self, offering_id: UUID) -> bool:
        return self._interno.try_release_slot(offering_id)

    def save(self, offering: CourseOffering) -> None:
        self._interno.save(offering)

    def update_capacity(
        self, offering_id: UUID, *, new_capacity: int, expected_version: int
    ) -> bool:
        return self._interno.update_capacity(
            offering_id, new_capacity=new_capacity, expected_version=expected_version
        )


class InMemoryEnrollmentRepository(EnrollmentRepository):
    """Repositorio de inscripciones respaldado por un diccionario."""

    def __init__(self, enrollments: list[Enrollment] | None = None) -> None:
        self._enrollments: dict[UUID, Enrollment] = {e.id: e for e in (enrollments or [])}
        self.guardados: list[UUID] = []

    def find_by_id(self, enrollment_id: UUID) -> Enrollment | None:
        return self._enrollments.get(enrollment_id)

    def find_active_by_student(
        self, student_id: UUID, enrollment_period_id: UUID
    ) -> list[Enrollment]:
        return [
            e
            for e in self._enrollments.values()
            if e.student_id == student_id
            and e.enrollment_period_id == enrollment_period_id
            and e.is_active()
        ]

    def find_by_student_and_offering(
        self, student_id: UUID, course_offering_id: UUID, enrollment_period_id: UUID
    ) -> Enrollment | None:
        return next(
            (
                e
                for e in self._enrollments.values()
                if e.student_id == student_id
                and e.course_offering_id == course_offering_id
                and e.enrollment_period_id == enrollment_period_id
            ),
            None,
        )

    def save(self, enrollment: Enrollment) -> None:
        self._enrollments[enrollment.id] = enrollment
        self.guardados.append(enrollment.id)


class FakeUnitOfWork(UnitOfWork):
    """Frontera transaccional de mentira que registra lo que se le pidio.

    Permite afirmar en un test que el caso de uso CONFIRMO la transaccion, o que salio sin
    confirmarla cuando algo fallo. Sin ese registro, un caso de uso que se olvidara del
    `commit` pasaria los tests unitarios y perderia todas las escrituras en produccion.
    """

    def __init__(self) -> None:
        self.confirmadas = 0
        self.revertidas = 0
        self.entradas = 0

    def __enter__(self) -> "FakeUnitOfWork":
        self.entradas += 1
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.revertidas += 1

    def commit(self) -> None:
        self.confirmadas += 1

    def rollback(self) -> None:
        self.revertidas += 1

    def flush(self) -> None:
        return None


class InMemoryAcademicHistory(AcademicHistoryReader):
    """Historial academico respaldado por un diccionario."""

    def __init__(self, aprobadas: dict[UUID, set[UUID]] | None = None) -> None:
        """Construye el doble.

        Args:
            aprobadas: identificadores de las materias aprobadas, por estudiante.
        """
        self._aprobadas = aprobadas or {}

    def find_approved_course_ids(self, student_id: UUID) -> set[UUID]:
        return self._aprobadas.get(student_id, set())
