"""Schemas de los endpoints de administración académica.

Siguen los ejemplos de `API.md` sección 6.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.interfaces.api.schemas.catalog_schemas import ScheduleBlockSchema


class CreateEnrollmentPeriodSchema(BaseModel):
    """Cuerpo de `POST /admin/enrollment-periods`.

    No incluye `is_active`: una ventana nace siempre cerrada y se abre con el endpoint de
    activación. Aceptarlo aquí permitiría crear una ventana ya abierta saltándose la
    desactivación de la anterior, que es lo que hace atómico el cambio de semestre.
    """

    code: str = Field(
        min_length=1,
        max_length=20,
        description="Código único de la ventana",
        examples=["2026-1-V1"],
    )
    academic_period: str = Field(
        min_length=1,
        max_length=20,
        description="Semestre al que pertenece",
        examples=["2026-1"],
    )
    name: str = Field(
        min_length=1,
        max_length=150,
        description="Nombre legible para el estudiante",
        examples=["Matrícula 2026-1 primera vuelta"],
    )
    starts_at: datetime = Field(description="Instante de apertura, en UTC")
    ends_at: datetime = Field(description="Instante de cierre, en UTC")


class EnrollmentPeriodSchema(BaseModel):
    """Una ventana de matrícula tal como la ve la administración."""

    id: UUID
    code: str
    academic_period: str
    name: str
    starts_at: datetime
    ends_at: datetime
    is_active: bool


class CreateCourseSchema(BaseModel):
    """Cuerpo de `POST /admin/courses`.

    El formato del código no se valida aquí sino en el value object `CourseCode`: la regla es
    del dominio, y duplicarla en el schema haría que dos sitios tuvieran que cambiarse a la vez
    el día que la institución la cambie.
    """

    code: str = Field(
        min_length=1,
        max_length=20,
        description="Código institucional de la materia",
        examples=["MAT101"],
    )
    name: str = Field(min_length=1, max_length=150, examples=["Cálculo I"])
    credits: int = Field(gt=0, description="Créditos académicos que otorga", examples=[4])
    description: str | None = Field(default=None, description="Descripción del contenido")


class CreateOfferingSchema(BaseModel):
    """Cuerpo de `POST /admin/offerings`.

    No incluye el período: el grupo se abre siempre en la ventana activa. Tampoco incluye
    `enrolled_count`, que nace en cero y solo lo mueve la inscripción.
    """

    course_id: UUID = Field(description="Materia que se dicta")
    professor_id: UUID | None = Field(default=None, description="Docente asignado, si ya se conoce")
    group_number: str = Field(
        min_length=1,
        max_length=10,
        description="Número de grupo dentro de la materia",
        examples=["02"],
    )
    total_capacity: int = Field(gt=0, description="Cupos totales del grupo", examples=[40])
    schedule: list[ScheduleBlockSchema] = Field(
        default_factory=list, description="Franjas semanales en las que se dicta"
    )


class UpdateCapacitySchema(BaseModel):
    """Cuerpo de `PUT /admin/offerings/{id}/capacity`.

    `gt=0` lo impone también el `CHECK (total_capacity > 0)` de PostgreSQL. Declararlo aquí
    convierte un 500 por violación de restricción en un 422 con el campo señalado.
    """

    total_capacity: int = Field(gt=0, description="Cupo total que debe quedar", examples=[45])
