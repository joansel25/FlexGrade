"""DTO del comprobante de matrícula.

Reúne en una sola estructura todo lo que el documento debe mostrar: quién se matriculó, en qué
período y qué materias quedaron inscritas. Se compone en la capa de aplicación y viaja hasta el
adaptador que lo dibuja, que así no necesita consultar nada por su cuenta.

Esa separación es la que permite cambiar el formato del comprobante —otra maquetación, otro
motor, incluso HTML en vez de PDF— sin tocar ninguna consulta, y probar el contenido del
comprobante sin generar un solo byte de PDF.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from uuid import UUID


@dataclass(frozen=True)
class ReceiptScheduleBlockDTO:
    """Una franja de clase dentro del comprobante.

    Attributes:
        day_of_week: día de la semana, de 1 (lunes) a 7 (domingo).
        start_time: hora de inicio.
        end_time: hora de fin.
        classroom: aula, si ya se asignó.
    """

    day_of_week: int
    start_time: time
    end_time: time
    classroom: str | None = None


@dataclass(frozen=True)
class ReceiptItemDTO:
    """Una materia inscrita, tal como aparece en el comprobante.

    Attributes:
        course_code: código de la materia (por ejemplo `MAT101`).
        course_name: nombre de la materia.
        credits: créditos que otorga.
        group_number: número del grupo.
        professor: nombre del docente, o `None` si aún no se ha asignado.
        schedule: franjas del grupo, ordenadas por día y hora.
    """

    course_code: str
    course_name: str
    credits: int
    group_number: str
    professor: str | None
    schedule: list[ReceiptScheduleBlockDTO] = field(default_factory=list)


@dataclass(frozen=True)
class ReceiptDTO:
    """Contenido completo del comprobante de matrícula.

    Attributes:
        student_code: código institucional del estudiante.
        student_name: nombre completo.
        program_code: código del programa (por ejemplo `ISIS`).
        program_name: nombre del programa.
        current_semester: semestre que cursa.
        enrollment_date: fecha de ingreso a la institución.
        academic_period: semestre al que corresponde la matrícula (por ejemplo `2025-2`).
        period_code: código de la ventana de matrícula.
        generated_at: instante en que se generó el documento. Va impreso porque un comprobante
            sin fecha no dice a qué momento corresponde, y durante la matrícula el contenido
            puede cambiar de un minuto al siguiente.
        items: las materias inscritas, ordenadas por código.
        total_credits: créditos inscritos.
        verification_code: código corto con el que Registro Académico puede localizar esta
            matrícula. No es una firma criptográfica y no pretende serlo: es una referencia
            legible, como un número de radicado.
    """

    student_id: UUID
    student_code: str
    student_name: str
    program_code: str
    program_name: str
    current_semester: int
    enrollment_date: date
    academic_period: str
    period_code: str
    generated_at: datetime
    verification_code: str
    items: list[ReceiptItemDTO] = field(default_factory=list)
    total_credits: int = 0
