"""Schemas de salida del perfil del estudiante."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class ProgramSummarySchema(BaseModel):
    """Programa académico tal como aparece anidado dentro de otras respuestas."""

    id: UUID
    code: str
    name: str


class StudentProfileSchema(BaseModel):
    """Respuesta 200 de `GET /students/me`.

    Sigue el contrato de `API.md`, ya con el bloque `program` anidado: la Fase 1 lo
    dejó como `program_id` plano por no existir todavía el repositorio de programas,
    y la Fase 2 lo completa.
    """

    id: UUID
    student_code: str
    full_name: str
    email: str
    program: ProgramSummarySchema
    current_semester: int = Field(ge=1)
    enrollment_date: date


class HistoryEntrySchema(BaseModel):
    """Una materia cursada, con su resultado."""

    course_id: UUID
    code: str
    name: str
    credits: int
    final_grade: Decimal
    status: str = Field(description="APPROVED o FAILED")


class HistoryPeriodSchema(BaseModel):
    """Lo cursado en un semestre.

    `average` es el promedio PONDERADO POR CRÉDITOS del semestre, no una media simple: una
    materia de cuatro créditos pesa el doble que una de dos, que es como se calcula en cualquier
    institución.
    """

    academic_period: str
    entries: list[HistoryEntrySchema] = Field(default_factory=list)
    credits_attempted: int
    credits_approved: int
    average: Decimal


class AcademicHistorySchema(BaseModel):
    """Respuesta de `GET /students/me/history`.

    Los semestres van del más reciente al más antiguo, que es como se lee un expediente. Un
    expediente vacío —`periods: []`— es una respuesta legítima y no un error: quien acaba de
    ingresar todavía no ha cerrado ningún semestre.
    """

    student_code: str
    full_name: str
    periods: list[HistoryPeriodSchema] = Field(default_factory=list)
    total_credits_approved: int
    cumulative_average: Decimal
