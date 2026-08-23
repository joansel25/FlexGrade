"""Schemas de salida del perfil del estudiante."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


class StudentProfileSchema(BaseModel):
    """Respuesta 200 de `GET /students/me`.

    Sigue el contrato de `API.md`. El bloque `program` que allí aparece anidado
    se completará en la Fase 2, cuando exista el repositorio de programas; por
    ahora se expone `program_id`, que es el dato que ya está disponible.
    """

    id: UUID
    student_code: str
    full_name: str
    email: str
    program_id: UUID
    current_semester: int = Field(ge=1)
    enrollment_date: date
