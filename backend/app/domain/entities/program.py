"""Entidad Program: el programa académico al que se adscribe un estudiante."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass
class Program:
    """Programa académico ofrecido por la institución.

    Determina dos cosas del estudiante: qué materias componen su plan de estudios y cuántos
    semestres dura su carrera.

    Attributes:
        id: identificador único del programa.
        code: código institucional corto (por ejemplo `ISIS`).
        name: nombre completo (por ejemplo `Ingeniería de Sistemas`).
        total_semesters: duración del plan de estudios en semestres.
        created_at: instante de creación del registro.
    """

    id: UUID
    code: str
    name: str
    total_semesters: int
    created_at: datetime | None = field(default=None)
