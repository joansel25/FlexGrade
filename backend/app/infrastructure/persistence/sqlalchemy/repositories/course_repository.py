"""Adaptador de `CourseRepository` sobre SQLAlchemy."""

from __future__ import annotations

import uuid as uuid_module
from collections import defaultdict
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import ColumnElement, Select, and_, delete, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.application.dtos.pagination import Page
from app.application.ports.repositories.course_repository import CourseRepository
from app.domain.entities.course import Course
from app.domain.entities.course_requirement import CourseRequirement
from app.domain.value_objects.course_code import CourseCode
from app.domain.value_objects.requirement_type import RequirementType
from app.infrastructure.persistence.sqlalchemy.models.course import CourseModel
from app.infrastructure.persistence.sqlalchemy.models.program_course import ProgramCourseModel
from app.infrastructure.persistence.sqlalchemy.models.program_course_requirement import (
    ProgramCourseRequirementModel,
)


class SQLAlchemyCourseRepository(CourseRepository):
    """Implementación del puerto del catálogo de materias contra PostgreSQL."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_id(self, course_id: UUID) -> Course | None:
        modelo = self._session.get(CourseModel, course_id)
        return self._a_entidad(modelo) if modelo is not None else None

    def find_by_code(self, code: CourseCode) -> Course | None:
        # Se compara contra el valor normalizado del value object: `CourseCode` ya pasó el
        # código a mayúsculas, así que la búsqueda es determinista.
        sentencia = select(CourseModel).where(CourseModel.code == code.value)
        modelo = self._session.execute(sentencia).scalar_one_or_none()
        return self._a_entidad(modelo) if modelo is not None else None

    def find_by_ids(self, course_ids: Sequence[UUID]) -> dict[UUID, Course]:
        if not course_ids:
            return {}

        sentencia = select(CourseModel).where(CourseModel.id.in_(course_ids))
        return {m.id: self._a_entidad(m) for m in self._session.execute(sentencia).scalars()}

    def find_requirements(self, course_id: UUID, program_id: UUID) -> list[CourseRequirement]:
        sentencia = (
            select(CourseModel, ProgramCourseRequirementModel.requirement_type)
            .join(
                ProgramCourseRequirementModel,
                ProgramCourseRequirementModel.required_course_id == CourseModel.id,
            )
            .where(ProgramCourseRequirementModel.program_id == program_id)
            .where(ProgramCourseRequirementModel.course_id == course_id)
            .order_by(CourseModel.code)
        )

        return [
            CourseRequirement(
                course=self._a_entidad(modelo),
                requirement_type=RequirementType(tipo),
            )
            for modelo, tipo in self._session.execute(sentencia).all()
        ]

    def find_requirements_for_courses(
        self, course_ids: Sequence[UUID], program_id: UUID
    ) -> dict[UUID, list[CourseRequirement]]:
        if not course_ids:
            return {}

        sentencia = (
            select(
                ProgramCourseRequirementModel.course_id,
                CourseModel,
                ProgramCourseRequirementModel.requirement_type,
            )
            .join(
                ProgramCourseRequirementModel,
                ProgramCourseRequirementModel.required_course_id == CourseModel.id,
            )
            .where(ProgramCourseRequirementModel.program_id == program_id)
            .where(ProgramCourseRequirementModel.course_id.in_(course_ids))
            .order_by(CourseModel.code)
        )

        por_materia: dict[UUID, list[CourseRequirement]] = defaultdict(list)

        for materia_id, modelo, tipo in self._session.execute(sentencia).all():
            por_materia[materia_id].append(
                CourseRequirement(
                    course=self._a_entidad(modelo),
                    requirement_type=RequirementType(tipo),
                )
            )

        # Se devuelve un `dict` normal y no el `defaultdict`: quien llama consulta materias que
        # pueden no tener requisitos, y con un `defaultdict` cada consulta fallida insertaría
        # una lista vacía y haría crecer el resultado por el mero hecho de leerlo.
        return dict(por_materia)

    def find_corequisite_dependents(self, course_id: UUID, program_id: UUID) -> list[Course]:
        # Filtra por `(program_id, required_course_id)`, que NO es prefijo de la clave
        # primaria: lo resuelve el índice `ix_program_course_requirements_required` que crea la
        # migración 0008. Sin él, PostgreSQL recorrería la tabla entera en cada cancelación.
        sentencia = (
            select(CourseModel)
            .join(
                ProgramCourseRequirementModel,
                ProgramCourseRequirementModel.course_id == CourseModel.id,
            )
            .where(ProgramCourseRequirementModel.program_id == program_id)
            .where(ProgramCourseRequirementModel.required_course_id == course_id)
            .where(
                ProgramCourseRequirementModel.requirement_type == RequirementType.COREQUISITE.value
            )
            .order_by(CourseModel.code)
        )

        return [self._a_entidad(m) for m in self._session.execute(sentencia).scalars()]

    def find_mutual_corequisites(self, course_id: UUID, program_id: UUID) -> set[UUID]:
        # Autojoin: `ida` son los correquisitos de la materia y `vuelta` comprueba que cada uno
        # de ellos la exija a su vez. Solo sobreviven los pares recíprocos, que son los que
        # forman bloque. Una consulta, no una por correquisito: esto corre dentro de la
        # transacción de inscripción.
        ida = ProgramCourseRequirementModel
        vuelta = aliased(ProgramCourseRequirementModel)

        sentencia = (
            select(ida.required_course_id)
            .join(
                vuelta,
                and_(
                    vuelta.program_id == ida.program_id,
                    vuelta.course_id == ida.required_course_id,
                    vuelta.required_course_id == ida.course_id,
                    vuelta.requirement_type == RequirementType.COREQUISITE.value,
                ),
            )
            .where(ida.program_id == program_id)
            .where(ida.course_id == course_id)
            .where(ida.requirement_type == RequirementType.COREQUISITE.value)
        )

        return set(self._session.execute(sentencia).scalars())

    def belongs_to_program(self, course_id: UUID, program_id: UUID) -> bool:
        # `exists()` y no un `count`: PostgreSQL se detiene en la primera coincidencia en vez
        # de recorrer todas, y la respuesta es la misma.
        sentencia = select(
            select(ProgramCourseModel.course_id)
            .where(ProgramCourseModel.course_id == course_id)
            .where(ProgramCourseModel.program_id == program_id)
            .exists()
        )
        return bool(self._session.execute(sentencia).scalar_one())

    def search(
        self,
        *,
        page: int,
        size: int,
        program_id: UUID | None = None,
        semester: int | None = None,
        search: str | None = None,
    ) -> Page[Course]:
        # Una única consulta de identificadores que satisfacen los filtros, reutilizada para
        # contar el total y para traer la página. Así los dos números no pueden discrepar:
        # duplicar las condiciones en dos consultas distintas es la forma clásica de acabar
        # con un `total` que no corresponde a los `items`.
        ids_filtrados = self._ids_que_cumplen(
            program_id=program_id, semester=semester, search=search
        )

        total = self._session.execute(
            select(func.count()).select_from(ids_filtrados.subquery())
        ).scalar_one()

        sentencia = (
            select(CourseModel)
            .where(CourseModel.id.in_(ids_filtrados))
            .order_by(CourseModel.code)
            .offset((page - 1) * size)
            .limit(size)
        )
        materias = [self._a_entidad(m) for m in self._session.execute(sentencia).scalars()]

        return Page(items=materias, total=total, page=page, size=size)

    def find_study_plan(self, program_id: UUID) -> list[tuple[Course, int, bool]]:
        # Un solo join: el plan entero cabe en una consulta porque `program_courses` ya
        # lleva el semestre y la obligatoriedad. Traer las materias y luego preguntar por
        # cada relación sería un N+1 sobre una pantalla que se abre entera de golpe.
        sentencia = (
            select(
                CourseModel,
                ProgramCourseModel.suggested_semester,
                ProgramCourseModel.is_mandatory,
            )
            .join(ProgramCourseModel, ProgramCourseModel.course_id == CourseModel.id)
            .where(ProgramCourseModel.program_id == program_id)
            .order_by(ProgramCourseModel.suggested_semester, CourseModel.code)
        )

        return [
            (self._a_entidad(modelo), semestre, obligatoria)
            for modelo, semestre, obligatoria in self._session.execute(sentencia).all()
        ]

    def find_requirement_dependents(self, course_id: UUID, program_id: UUID) -> list[Course]:
        # Sin filtrar por tipo, al contrario que `find_corequisite_dependents`: aquí importa
        # quién la exige de cualquier manera. Lo resuelve el mismo índice inverso de la
        # migración 0008.
        sentencia = (
            select(CourseModel)
            .join(
                ProgramCourseRequirementModel,
                ProgramCourseRequirementModel.course_id == CourseModel.id,
            )
            .where(ProgramCourseRequirementModel.program_id == program_id)
            .where(ProgramCourseRequirementModel.required_course_id == course_id)
            .order_by(CourseModel.code)
        )

        return [self._a_entidad(m) for m in self._session.execute(sentencia).scalars()]

    def save_plan_entry(
        self,
        *,
        program_id: UUID,
        course_id: UUID,
        suggested_semester: int,
        is_mandatory: bool,
    ) -> None:
        # `merge` y no `add`: la clave primaria es compuesta y ya puede existir. Con `add`,
        # cambiar el semestre de una materia que ya está en el plan fallaría por clave
        # duplicada en vez de actualizarla.
        self._session.merge(
            ProgramCourseModel(
                program_id=program_id,
                course_id=course_id,
                suggested_semester=suggested_semester,
                is_mandatory=is_mandatory,
            )
        )

    def remove_plan_entry(self, *, program_id: UUID, course_id: UUID) -> bool:
        sentencia = delete(ProgramCourseModel).where(
            ProgramCourseModel.program_id == program_id,
            ProgramCourseModel.course_id == course_id,
        )

        return self._session.execute(sentencia).rowcount > 0

    def save(self, course: Course) -> None:
        # `merge` y no `add`: sirve tanto para una materia nueva como para una que ya existe,
        # que es lo que promete el puerto. Con `add`, guardar una materia leída antes en esta
        # misma sesión fallaría con clave duplicada.
        self._session.merge(
            CourseModel(
                id=course.id,
                code=course.code.value,
                name=course.name,
                credits=course.credits,
                description=course.description,
            )
        )

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _ids_que_cumplen(
        *, program_id: UUID | None, semester: int | None, search: str | None
    ) -> Select[tuple[uuid_module.UUID]]:
        """Construye la consulta de los identificadores que pasan los filtros.

        Devuelve identificadores distintos, no filas: el join con `program_courses` repetiría
        una materia que aparezca en varios planes de estudio, y ese duplicado inflaría el
        total y llenaría la página con la misma materia dos veces.
        """
        sentencia = select(CourseModel.id)

        # El join solo se añade si algún filtro lo necesita. Unirse a `program_courses` sin
        # necesidad excluiría del catálogo las materias que todavía no pertenecen a ningún
        # plan de estudios, que sí deben aparecer en el listado completo.
        if program_id is not None or semester is not None:
            sentencia = sentencia.join(
                ProgramCourseModel, ProgramCourseModel.course_id == CourseModel.id
            )

        if program_id is not None:
            sentencia = sentencia.where(ProgramCourseModel.program_id == program_id)

        if semester is not None:
            sentencia = sentencia.where(ProgramCourseModel.suggested_semester == semester)

        if search and search.strip():
            # `ilike` ignora mayúsculas; `unaccent` ignora las tildes. Hacen falta las dos: en
            # un catálogo en español casi nadie escribe «Cálculo» con tilde al buscar, y sin
            # `unaccent` esa búsqueda devolvería cero resultados justo en las materias más
            # buscadas. Se aplica a los dos lados —al dato y al patrón— porque el usuario
            # puede escribirlo con tilde o sin ella.
            #
            # El texto del usuario viaja como parámetro enlazado, nunca interpolado en el SQL.
            patron = f"%{search.strip()}%"
            sin_tildes = func.unaccent(patron)
            coincide: ColumnElement[bool] = or_(
                func.unaccent(CourseModel.name).ilike(sin_tildes),
                func.unaccent(CourseModel.code).ilike(sin_tildes),
            )
            sentencia = sentencia.where(coincide)

        return sentencia.distinct()

    @staticmethod
    def _a_entidad(modelo: CourseModel) -> Course:
        """Convierte el modelo ORM en la entidad del dominio."""
        return Course(
            id=modelo.id,
            code=CourseCode(modelo.code),
            name=modelo.name,
            credits=modelo.credits,
            description=modelo.description,
            created_at=modelo.created_at,
        )
