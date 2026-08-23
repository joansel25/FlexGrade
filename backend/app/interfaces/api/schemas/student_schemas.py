"""Schemas de salida del perfil del estudiante."""

from __future__ import annotations

from datetime import date
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
