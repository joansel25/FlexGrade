"""Schemas de entrada y salida de la inscripción y del horario.

Siguen literalmente los ejemplos de `API.md` secciones 2 y 4.
"""

from __future__ import annotations

from datetime import datetime, time
from uuid import UUID

from pydantic import BaseModel, Field


class EnrollRequestSchema(BaseModel):
    """Cuerpo de `POST /enrollments`.

    Solo lleva el grupo. El estudiante NO viaja en la petición: sale del token. Aceptarlo del
    cliente permitiría a cualquiera inscribir a otra persona, que es el fallo de autorización
    más común en este tipo de sistemas.
    """

    course_offering_id: UUID = Field(description="Grupo en el que inscribirse")


class EnrollmentSchema(BaseModel):
    """Respuesta 201 de `POST /enrollments`."""

    id: UUID
    student_id: UUID
    course_offering_id: UUID
    course_code: str
    course_name: str
    group_number: str
    enrolled_at: datetime | None
    status: str


class ScheduleBlockSchema(BaseModel):
    """Una franja del horario del estudiante."""

    course_code: str
    course_name: str
    group_number: str
    professor: str | None = None
    day_of_week: int = Field(ge=1, le=7, description="1 = lunes … 7 = domingo (ISO 8601)")
    start_time: time
    end_time: time
    classroom: str | None = None


class StudentScheduleSchema(BaseModel):
    """Respuesta 200 de `GET /students/me/schedule`.

    Attributes:
        period: semestre al que corresponde el horario (por ejemplo `2025-2`).
        blocks: las franjas, ordenadas por día y hora.
    """

    period: str
    blocks: list[ScheduleBlockSchema] = Field(default_factory=list)
