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


class OfferingScheduleSchema(BaseModel):
    """Una franja del horario de un grupo, sin el contexto de la materia.

    Se distingue de `ScheduleBlockSchema` a propósito: allí cada franja repite el código y el
    nombre de la materia porque el horario mezcla las de varios grupos y hay que saber a qué
    clase ir. Aquí las franjas ya viven DENTRO de su inscripción, así que repetirlo sería
    duplicar el mismo dato en cada franja.
    """

    day_of_week: int = Field(ge=1, le=7, description="1 = lunes … 7 = domingo (ISO 8601)")
    start_time: time
    end_time: time
    classroom: str | None = None


class StudentEnrollmentSchema(BaseModel):
    """Una inscripción activa del estudiante, con lo necesario para poder cancelarla.

    Lleva `id` —el de la INSCRIPCIÓN, no el del grupo— porque es lo que exige
    `DELETE /enrollments/{id}`. El horario no lo incluye: sus franjas se leen, no se cancelan.
    """

    id: UUID
    course_offering_id: UUID
    course_id: UUID
    course_code: str
    course_name: str
    credits: int
    group_number: str
    professor: str | None = None
    schedule: list[OfferingScheduleSchema] = Field(default_factory=list)
    enrolled_at: datetime | None = None
    pending_corequisites: list[str] = Field(
        default_factory=list,
        description="Códigos que esta materia exige cursar a la vez y aún no están inscritos",
    )


class CancelledEnrollmentSchema(BaseModel):
    """Una inscripción que quedó cancelada."""

    id: UUID
    course_offering_id: UUID
    course_code: str
    course_name: str
    group_number: str


class CancellationSchema(BaseModel):
    """Respuesta de `DELETE /enrollments/{id}`.

    Devuelve una LISTA porque cancelar puede arrastrar más de una inscripción: las materias
    unidas por correquisitos mutuos se abandonan como un bloque, igual que se cursan como un
    bloque. El endpoint respondía `204 No Content` hasta esta iteración; con el arrastre, ese
    silencio dejaría que dos materias desaparecieran de la pantalla tras pulsar «Cancelar» en
    una sola, y eso se lee como una avería.

    Attributes:
        cancelled: lo que quedó cancelado, empezando por la inscripción que se pidió.
    """

    cancelled: list[CancelledEnrollmentSchema] = Field(default_factory=list)


class StudentEnrollmentsSchema(BaseModel):
    """Respuesta de `GET /students/me/enrollments`.

    Attributes:
        period: semestre al que corresponden (por ejemplo `2025-2`).
        period_code: código de la ventana de matrícula.
        items: las inscripciones activas, ordenadas por código de materia.
        total_credits: créditos inscritos. Se calcula en el servidor para que la cifra sea la
            misma en la pantalla y en el comprobante en PDF.
    """

    period: str
    period_code: str
    items: list[StudentEnrollmentSchema] = Field(default_factory=list)
    total_credits: int
