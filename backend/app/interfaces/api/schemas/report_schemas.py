"""Schemas de los reportes de administración.

Siguen el ejemplo de `API.md` sección 6. `generated_at` viaja en todas las respuestas: un
reporte sin la hora a la que se calculó es un número sin contexto, y estas cifras cambian cada
segundo durante la ventana de matrícula.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ReportTotalsSchema(BaseModel):
    """Cifras globales del período."""

    total_enrollments: int = Field(description="Inscripciones activas del período")
    unique_students: int = Field(description="Estudiantes distintos con al menos una activa")
    active_offerings: int = Field(description="Grupos con al menos una inscripción activa")


class ProgramEnrollmentsSchema(BaseModel):
    """Inscripciones de un programa dentro del período."""

    program_code: str
    program_name: str
    enrollments: int
    students: int


class EnrollmentReportSchema(BaseModel):
    """Respuesta de `GET /admin/reports/enrollments`."""

    period_code: str
    generated_at: datetime
    totals: ReportTotalsSchema
    by_program: list[ProgramEnrollmentsSchema] = Field(default_factory=list)


class OfferingOccupancySchema(BaseModel):
    """Ocupación de un grupo.

    `occupancy_rate` viaja calculado —porcentaje de 0 a 100 con dos decimales— para que la
    interfaz no tenga que repetir la división, y con ella el criterio de redondeo.
    """

    offering_id: UUID
    course_code: str
    course_name: str
    group_number: str
    total_capacity: int
    enrolled_count: int
    available_slots: int
    occupancy_rate: float


class OccupancyReportSchema(BaseModel):
    """Respuesta de `GET /admin/reports/occupancy`.

    Va paginada, a diferencia del reporte de inscripciones: los programas de la institución son
    decenas, pero los grupos de un período son cientos y crecen cada semestre. `total`, `page` y
    `size` acompañan a la lista con la misma semántica que en el resto de la API.
    """

    period_code: str
    generated_at: datetime
    offerings: list[OfferingOccupancySchema] = Field(default_factory=list)
    total: int
    page: int
    size: int
