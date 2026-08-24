"""Schemas de los endpoints de administración académica.

Siguen los ejemplos de `API.md` sección 6.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


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
