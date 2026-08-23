"""Entidad Student: el perfil académico asociado a una cuenta."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from uuid import UUID

from app.domain.value_objects.student_code import StudentCode


@dataclass
class Student:
    """Perfil académico del estudiante.

    Vincula una cuenta (`user_id`) con un programa y con los datos académicos que
    el resto del dominio necesita: el semestre en curso condiciona qué materias
    puede inscribir, y el programa determina qué catálogo le corresponde.

    Attributes:
        id: identificador único del perfil.
        user_id: cuenta de autenticación a la que pertenece.
        student_code: código institucional, validado como value object.
        program_id: programa académico al que está adscrito.
        current_semester: semestre que cursa actualmente (>= 1).
        full_name: nombre completo.
        enrollment_date: fecha de ingreso a la institución.
        created_at: instante de creación del registro.
    """

    id: UUID
    user_id: UUID
    student_code: StudentCode
    program_id: UUID
    current_semester: int
    full_name: str
    enrollment_date: date
    created_at: datetime | None = field(default=None)

    def belongs_to_program(self, program_id: UUID) -> bool:
        """Indica si el estudiante pertenece al programa indicado.

        Lo usará la validación de inscripción en la Fase 3: una materia solo se
        puede inscribir si pertenece al plan de estudios del propio programa.
        """
        return self.program_id == program_id
