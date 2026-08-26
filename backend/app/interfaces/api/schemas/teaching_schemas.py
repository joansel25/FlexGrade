"""Schemas de la carga docente (Fase 9)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.interfaces.api.schemas.catalog_schemas import ScheduleBlockSchema


class ProfessorOfferingSchema(BaseModel):
    """Un grupo visto por quien lo dicta.

    Se parece a `OfferingSchema` pero NO es el mismo, y unificarlos sería un error. Aquel es la
    vista del catálogo: lo que le importa a quien busca dónde matricularse, y por eso lleva
    `available_slots` y el nombre del docente. Aquí el docente es quien mira, así que su propio
    nombre sobra, los cupos libres no le sirven para nada y en cambio necesita la materia —que
    en el catálogo ya venía dada por el contexto— y cuántos estudiantes tiene enfrente.
    """

    offering_id: UUID
    course_id: UUID
    course_code: str
    course_name: str
    credits: int
    group_number: str
    enrolled_count: int
    total_capacity: int
    schedule: list[ScheduleBlockSchema] = Field(default_factory=list)


class ProfessorOfferingsSchema(BaseModel):
    """Respuesta de `GET /professors/me/offerings`.

    `period_code` en `null` significa que no hay ventana activa, que entre semestres es normal.
    Distingue ese caso de «hay semestre y no tengo carga», que se ve igual —una lista vacía— y
    quiere decir algo muy distinto.
    """

    period_code: str | None = None
    academic_period: str | None = None
    items: list[ProfessorOfferingSchema] = Field(default_factory=list)
    total: int
