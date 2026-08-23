"""Entidad Course: la materia del catálogo académico."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.domain.value_objects.course_code import CourseCode


@dataclass
class Course:
    """Materia del catálogo, independiente del semestre en que se dicte.

    La materia es la definición (`Cálculo I`, 4 créditos); los grupos concretos que se abren
    en un período son `CourseOffering`.

    No lleva sus prerrequisitos como atributo. Son una consulta aparte del repositorio
    (`find_prerequisites`) porque el listado del catálogo muestra decenas de materias y
    ninguna necesita esa información: cargarla siempre sería trabajo desperdiciado en la
    consulta más frecuente para servir al endpoint de detalle, que es el menos frecuente.

    Attributes:
        id: identificador único de la materia.
        code: código institucional, validado como value object.
        name: nombre completo de la materia.
        credits: créditos académicos que otorga.
        description: descripción del contenido, si la tiene.
        created_at: instante de creación del registro.
    """

    id: UUID
    code: CourseCode
    name: str
    credits: int
    description: str | None = None
    created_at: datetime | None = field(default=None)
