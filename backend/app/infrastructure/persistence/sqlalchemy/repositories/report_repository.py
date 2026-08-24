"""Adaptador de `ReportReader` sobre SQLAlchemy.

Todas las consultas de este adaptador agregan en PostgreSQL con `GROUP BY` y devuelven cifras
ya calculadas. Ninguna trae filas para contarlas en Python: el reporte se consulta durante la
ventana de matrícula, cuando la tabla `enrollments` tiene millones de filas y la base de datos
es el recurso que hay que cuidar.
"""

from __future__ import annotations

from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.application.dtos.pagination import Page
from app.application.dtos.report_dto import (
    OfferingOccupancyDTO,
    ProgramEnrollmentsDTO,
    ReportTotalsDTO,
)
from app.application.ports.repositories.report_repository import ReportReader
from app.domain.value_objects.enrollment_status import EnrollmentStatus
from app.infrastructure.persistence.sqlalchemy.models.course import CourseModel
from app.infrastructure.persistence.sqlalchemy.models.course_offering import CourseOfferingModel
from app.infrastructure.persistence.sqlalchemy.models.enrollment import EnrollmentModel
from app.infrastructure.persistence.sqlalchemy.models.program import ProgramModel
from app.infrastructure.persistence.sqlalchemy.models.student import StudentModel

# El filtro comun se aplica a consultas que seleccionan columnas distintas, asi que el
# helper conserva el tipo exacto de la que recibe en vez de aplanarlo: `mypy` sigue
# sabiendo que columnas trae cada fila al leer el resultado.
_ConsultaT = TypeVar("_ConsultaT", bound=Select[Any])


class SQLAlchemyReportRepository(ReportReader):
    """Implementación de las consultas agregadas de administración contra PostgreSQL."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def enrollment_totals(self, enrollment_period_id: UUID) -> ReportTotalsDTO:
        # Una sola consulta con tres agregados, no tres consultas. Recorrer la misma tabla y
        # el mismo filtro tres veces multiplicaría por tres el trabajo para obtener cifras que
        # además podrían no corresponder al mismo instante.
        sentencia = select(
            func.count(),
            func.count(func.distinct(EnrollmentModel.student_id)),
            func.count(func.distinct(EnrollmentModel.course_offering_id)),
        ).select_from(EnrollmentModel)

        inscripciones, estudiantes, grupos = self._session.execute(
            self._solo_activas(sentencia, enrollment_period_id)
        ).one()

        return ReportTotalsDTO(
            total_enrollments=int(inscripciones),
            unique_students=int(estudiantes),
            active_offerings=int(grupos),
        )

    def enrollments_by_program(self, enrollment_period_id: UUID) -> list[ProgramEnrollmentsDTO]:
        inscripciones = func.count().label("inscripciones")
        estudiantes = func.count(func.distinct(EnrollmentModel.student_id)).label("estudiantes")

        sentencia = (
            select(ProgramModel.code, ProgramModel.name, inscripciones, estudiantes)
            .select_from(EnrollmentModel)
            .join(StudentModel, StudentModel.id == EnrollmentModel.student_id)
            .join(ProgramModel, ProgramModel.id == StudentModel.program_id)
            .group_by(ProgramModel.id, ProgramModel.code, ProgramModel.name)
            # Del programa con más inscripciones al que menos; el código desempata para que dos
            # programas empatados salgan siempre en el mismo orden y el reporte sea reproducible.
            .order_by(inscripciones.desc(), ProgramModel.code)
        )

        filas = self._session.execute(self._solo_activas(sentencia, enrollment_period_id)).all()

        return [
            ProgramEnrollmentsDTO(
                program_code=fila.code,
                program_name=fila.name,
                enrollments=int(fila.inscripciones),
                students=int(fila.estudiantes),
            )
            for fila in filas
        ]

    def offering_occupancy(
        self, enrollment_period_id: UUID, *, page: int, size: int
    ) -> Page[OfferingOccupancyDTO]:
        total = self._session.execute(
            select(func.count())
            .select_from(CourseOfferingModel)
            .where(CourseOfferingModel.enrollment_period_id == enrollment_period_id)
        ).scalar_one()

        # La ocupación se ordena en SQL y se calcula en el DTO. Ordenar aquí es obligatorio
        # —paginar exige que el orden lo aplique la base de datos, no la página ya recortada—,
        # y `* 1.0` fuerza la división real: sin él PostgreSQL divide enteros y todos los
        # grupos por debajo del 100 % empatarían en cero.
        ocupacion = CourseOfferingModel.enrolled_count * 1.0 / CourseOfferingModel.total_capacity

        sentencia = (
            select(
                CourseOfferingModel.id,
                CourseModel.code,
                CourseModel.name,
                CourseOfferingModel.group_number,
                CourseOfferingModel.total_capacity,
                CourseOfferingModel.enrolled_count,
            )
            .join(CourseModel, CourseModel.id == CourseOfferingModel.course_id)
            .where(CourseOfferingModel.enrollment_period_id == enrollment_period_id)
            .order_by(ocupacion.desc(), CourseModel.code, CourseOfferingModel.group_number)
            .offset((page - 1) * size)
            .limit(size)
        )

        grupos = [
            OfferingOccupancyDTO(
                offering_id=fila.id,
                course_code=fila.code,
                course_name=fila.name,
                group_number=fila.group_number,
                total_capacity=fila.total_capacity,
                enrolled_count=fila.enrolled_count,
            )
            for fila in self._session.execute(sentencia).all()
        ]

        return Page(items=grupos, total=total, page=page, size=size)

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _solo_activas(sentencia: _ConsultaT, period_id: UUID) -> _ConsultaT:
        """Añade el filtro común de los reportes de inscripción: período y estado activo.

        Está en un helper porque las dos consultas tienen que filtrar EXACTAMENTE igual. Si una
        contara las canceladas y la otra no, los totales no cuadrarían con la suma del desglose
        por programa y nadie sabría cuál de los dos números creerse.
        """
        return sentencia.where(
            EnrollmentModel.enrollment_period_id == period_id,
            EnrollmentModel.status == EnrollmentStatus.ENROLLED.value,
        )
