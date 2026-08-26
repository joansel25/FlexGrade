"""DTOs del expediente académico (iteración 9.4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.domain.entities.course import Course
from app.domain.value_objects.grade import Grade
from app.domain.value_objects.history_status import HistoryStatus


@dataclass(frozen=True)
class HistoryEntryDTO:
    """Una materia cursada, con su resultado.

    Lleva la MATERIA entera y no solo su código porque el expediente muestra nombre y créditos,
    y pedirlos aparte obligaría a la interfaz a cruzar dos listas para pintar una fila.

    Attributes:
        course: la materia.
        final_grade: la nota con la que terminó.
        status: aprobada o perdida.
    """

    course: Course
    final_grade: Grade
    status: HistoryStatus


@dataclass(frozen=True)
class HistoryPeriodDTO:
    """Lo cursado en un semestre.

    Se agrupa por semestre y no se devuelve una lista plana porque así es como se lee un
    expediente: nadie pregunta «qué he cursado» sin querer saber cuándo. Y el promedio de un
    semestre concreto solo tiene sentido dentro de su grupo.

    Attributes:
        academic_period: el semestre, por ejemplo `2025-2`.
        entries: las materias, ordenadas por código.
        credits_attempted: créditos cursados en el semestre, aprobados o no.
        credits_approved: cuántos de ellos se aprobaron.
        average: promedio PONDERADO POR CRÉDITOS del semestre.
    """

    academic_period: str
    entries: list[HistoryEntryDTO] = field(default_factory=list)
    credits_attempted: int = 0
    credits_approved: int = 0
    average: Decimal = Decimal("0.00")


@dataclass(frozen=True)
class AcademicHistoryDTO:
    """El expediente completo.

    **El promedio es ponderado por créditos y no una media simple.** Una materia de cuatro
    créditos pesa el doble que una de dos, que es como se calcula en cualquier institución: la
    media simple daría un número que no coincide con el certificado oficial, y quien lo viera lo
    tomaría por bueno.

    Attributes:
        student_code: código institucional de quien consulta.
        full_name: su nombre.
        periods: los semestres, del más reciente al más antiguo.
        total_credits_approved: créditos aprobados en toda la carrera.
        cumulative_average: promedio acumulado, ponderado por créditos.
    """

    student_code: str
    full_name: str
    periods: list[HistoryPeriodDTO] = field(default_factory=list)
    total_credits_approved: int = 0
    cumulative_average: Decimal = Decimal("0.00")
