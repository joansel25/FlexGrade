"""Schemas de la carga docente (Fase 9)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
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


class GradeEntrySchema(BaseModel):
    """Una fila de la lista del grupo.

    `final_grade` en `null` significa «todavía sin calificar», y es distinto de `0.00`. Son
    estados opuestos —uno es que falta trabajo, el otro es una nota reprobatoria— y con un cero
    por defecto se verían igual. Es la misma razón por la que la columna es NULLABLE.
    """

    student_id: UUID
    student_code: str
    full_name: str
    final_grade: Decimal | None = None
    graded_at: datetime | None = None


class OfferingRosterSchema(BaseModel):
    """Respuesta de `GET /professors/me/offerings/{id}/roster`."""

    offering_id: UUID
    course_code: str
    course_name: str
    group_number: str
    entries: list[GradeEntrySchema] = Field(default_factory=list)
    total: int
    #: Cuántas quedan sin calificar. Viene calculado para que la interfaz no recorra la lista, y
    #: es la cifra que le dice al docente si ya terminó.
    pending: int


class SetGradeSchema(BaseModel):
    """Cuerpo de `PUT /professors/me/offerings/{id}/grades/{student_id}`.

    El rango se declara aquí Y en el value object `Grade` Y en un `CHECK` de la base. No es
    redundancia por descuido: Pydantic da el error de formato antes de tocar el dominio, `Grade`
    protege cualquier otro camino que escriba una nota —el seed, una migración, un caso de uso
    futuro— y el `CHECK` es la red final. Es la misma filosofía de defensas superpuestas que
    sostiene el control de cupos.
    """

    final_grade: Decimal = Field(
        ge=0,
        le=5,
        max_digits=3,
        decimal_places=2,
        description="Nota final en la escala de 0.0 a 5.0. Aprueba desde 3.0",
        examples=["4.20"],
    )
