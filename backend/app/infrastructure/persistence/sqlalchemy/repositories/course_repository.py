"""Adaptador de `CourseRepository` sobre SQLAlchemy."""

from __future__ import annotations

import uuid as uuid_module
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.orm import Session

from app.application.dtos.pagination import Page
from app.application.ports.repositories.course_repository import CourseRepository
from app.domain.entities.course import Course
from app.domain.value_objects.course_code import CourseCode
from app.infrastructure.persistence.sqlalchemy.models.course import CourseModel
from app.infrastructure.persistence.sqlalchemy.models.course_prerequisite import (
    CoursePrerequisiteModel,
)
from app.infrastructure.persistence.sqlalchemy.models.program_course import ProgramCourseModel


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

    def find_prerequisites(self, course_id: UUID) -> list[Course]:
        sentencia = (
            select(CourseModel)
            .join(
                CoursePrerequisiteModel,
                CoursePrerequisiteModel.required_course_id == CourseModel.id,
            )
            .where(CoursePrerequisiteModel.course_id == course_id)
            .order_by(CourseModel.code)
        )
        return [self._a_entidad(m) for m in self._session.execute(sentencia).scalars()]

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
