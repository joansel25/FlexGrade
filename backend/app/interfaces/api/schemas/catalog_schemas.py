"""Schemas de salida del catálogo académico.

Siguen literalmente los ejemplos de `API.md` sección 3. Los nombres de campo son los del
contrato, no los internos: el frontend ya está escrito contra ellos.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageSchema(BaseModel, Generic[T]):
    """Envoltorio de las respuestas paginadas (`API.md`, «Convenciones generales»).

    Attributes:
        items: los elementos de esta página.
        total: total de coincidencias, no solo las de esta página.
        page: número de página, empezando en 1.
        size: tamaño de página aplicado. Puede diferir del solicitado si excedía el máximo.
    """

    items: list[T]
    total: int
    page: int
    size: int


class CourseSchema(BaseModel):
    """Una materia del catálogo."""

    id: UUID
    code: str
    name: str
    credits: int
    description: str | None = None


class CourseDetailSchema(CourseSchema):
    """Detalle de una materia, con lo que exige dentro de un plan de estudios.

    Las dos listas solo se llenan cuando la petición indica `program_id`. Un requisito
    académico pertenece al plan, no al catálogo: la misma materia puede exigir `MAT101` en
    Ingeniería y nada en un plan donde entra como electiva, así que sin programa no hay una
    respuesta correcta que dar. `program_id` vuelve en la respuesta para que dos listas vacías
    no sean ambiguas: dicen «no exige nada EN ESTE PLAN», o «nadie preguntó por un plan».
    """

    program_id: UUID | None = Field(
        default=None, description="Plan sobre el que se resolvieron los requisitos"
    )
    prerequisites: list[CourseSchema] = Field(
        default_factory=list, description="Materias que hay que haber APROBADO antes"
    )
    corequisites: list[CourseSchema] = Field(
        default_factory=list, description="Materias que hay que cursar EN EL MISMO período"
    )


class ScheduleBlockSchema(BaseModel):
    """Una franja horaria de un grupo."""

    day_of_week: int = Field(ge=1, le=7, description="1 = lunes … 7 = domingo (ISO 8601)")
    start_time: time
    end_time: time
    classroom: str | None = None


class OfferingSchema(BaseModel):
    """Un grupo de una materia.

    `available_slots` se calcula en el dominio y viaja resuelto para que el frontend no tenga
    que restar. `enrolled_count` y, por tanto, `available_slots`, se leen siempre en vivo de
    la base de datos: nunca proceden de la caché.
    """

    id: UUID
    group_number: str
    professor: str | None = Field(default=None, description="Nombre del docente, si hay uno")
    total_capacity: int
    enrolled_count: int
    available_slots: int
    schedule: list[ScheduleBlockSchema] = Field(default_factory=list)


class CourseOfferingsSchema(BaseModel):
    """Respuesta de `GET /courses/{id}/offerings`."""

    course_id: UUID
    course_code: str
    period_code: str
    offerings: list[OfferingSchema] = Field(default_factory=list)


class OfferingDetailSchema(OfferingSchema):
    """Respuesta de `GET /offerings/{id}`, con el contexto de materia y período."""

    course_id: UUID
    enrollment_period_id: UUID


class CurrentPeriodSchema(BaseModel):
    """Respuesta de `GET /enrollment-periods/current`.

    Attributes:
        is_active: si un administrador ha activado la ventana.
        is_open: si admite inscripciones en este instante. No es lo mismo que `is_active`: una
            ventana activada puede no haber empezado todavía o haber cerrado ya, y esa
            distinción es la que permite mostrar «la matrícula abre el martes».
        time_remaining_seconds: segundos hasta el cierre; `0` si ya cerró.
    """

    id: UUID
    code: str
    academic_period: str
    name: str
    starts_at: datetime
    ends_at: datetime
    is_active: bool
    is_open: bool
    time_remaining_seconds: int


class StudyPlanEntrySchema(CourseSchema):
    """Una materia dentro del plan de estudios.

    Extiende `CourseSchema` con los dos datos que NO son de la materia sino de su relación
    con el programa: la misma materia puede ser de primer semestre y obligatoria en una
    carrera, y de tercero y electiva en otra.
    """

    suggested_semester: int = Field(ge=1, description="Semestre en que el plan la sugiere")
    is_mandatory: bool = Field(description="Obligatoria para graduarse, o electiva")


class StudyPlanSchema(BaseModel):
    """Respuesta de `GET /students/me/study-plan`.

    Va sin paginar, al contrario que el catálogo: un plan tiene decenas de materias y su
    valor está en verse entero. La pregunta que responde es «qué me falta para graduarme», y
    esa no se contesta de veinte en veinte.
    """

    program_id: UUID
    program_code: str
    program_name: str
    total_semesters: int
    courses: list[StudyPlanEntrySchema] = Field(default_factory=list)
    total_credits: int
