"""DTOs de los reportes de administración (`API.md` sección 6).

Un reporte no es una entidad ni una colección de entidades: es el resultado de agregar varias
tablas —inscripciones, estudiantes, programas, grupos— en cifras que no pertenecen a ningún
agregado del dominio. Modelarlo como entidad obligaría a inventar una que nadie persiste; por
eso vive aquí, como estructura de solo lectura.

Las cifras se calculan **siempre en vivo**. Un reporte cacheado durante la ventana de matrícula
mostraría una foto vieja justo cuando el dato cambia cada segundo, que es exactamente cuando
alguien lo está mirando para decidir si amplía un cupo.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class ReportTotalsDTO:
    """Cifras globales del período.

    Attributes:
        total_enrollments: inscripciones activas del período. Las canceladas no cuentan: no
            ocupan cupo ni aparecen en el horario de nadie.
        unique_students: personas distintas con al menos una inscripción activa. No coincide
            con `total_enrollments` —cada estudiante inscribe varias materias— y es la cifra
            que responde «cuánta gente ha matriculado ya».
        active_offerings: grupos con al menos una inscripción activa. No son los grupos
            abiertos: un grupo publicado al que nadie entró todavía no aparece aquí.
    """

    total_enrollments: int
    unique_students: int
    active_offerings: int


@dataclass(frozen=True)
class ProgramEnrollmentsDTO:
    """Inscripciones de un programa académico dentro del período.

    Attributes:
        program_code: código del programa (por ejemplo `ISIS`).
        program_name: nombre del programa.
        enrollments: inscripciones activas de sus estudiantes.
        students: estudiantes distintos del programa con al menos una inscripción activa.
    """

    program_code: str
    program_name: str
    enrollments: int
    students: int


@dataclass(frozen=True)
class EnrollmentReportDTO:
    """Resultado de `GET /admin/reports/enrollments`.

    Attributes:
        period_code: código de la ventana de matrícula sobre la que se calculó.
        generated_at: instante en que se calcularon las cifras. Va en la respuesta porque un
            reporte sin fecha es un número sin contexto: quien lo lee no sabe si mira el
            estado de hace un segundo o el de hace una hora.
        totals: cifras globales.
        by_program: desglose por programa, del que más inscripciones tiene al que menos.
    """

    period_code: str
    generated_at: datetime
    totals: ReportTotalsDTO
    by_program: list[ProgramEnrollmentsDTO] = field(default_factory=list)


@dataclass(frozen=True)
class OfferingOccupancyDTO:
    """Ocupación de un grupo concreto.

    Lleva el código y el nombre de la materia además del grupo porque un reporte que dijera
    «grupo 02 al 97 %» no permite actuar: hay que saber de qué materia se habla para decidir
    si se amplía el cupo o se abre otro grupo.

    Attributes:
        offering_id: identificador del grupo, con el que se puede llamar directamente a
            `PUT /admin/offerings/{id}/capacity`.
        course_code: código de la materia.
        course_name: nombre de la materia.
        group_number: número del grupo.
        total_capacity: cupos totales.
        enrolled_count: cupos ocupados, leídos en vivo del contador del grupo.
    """

    offering_id: UUID
    course_code: str
    course_name: str
    group_number: str
    total_capacity: int
    enrolled_count: int

    @property
    def available_slots(self) -> int:
        """Cupos libres; nunca negativo."""
        return max(0, self.total_capacity - self.enrolled_count)

    @property
    def occupancy_rate(self) -> float:
        """Porcentaje de cupo utilizado, de 0 a 100, con dos decimales.

        El `CHECK (total_capacity > 0)` del esquema hace imposible el denominador cero, pero la
        guarda se queda igualmente: un DTO que se puede construir en un test con cualquier
        valor no debería poder reventar con `ZeroDivisionError` en el sitio donde se calcula
        la cifra que alguien va a leer.
        """
        if self.total_capacity <= 0:
            return 0.0

        return round(self.enrolled_count * 100 / self.total_capacity, 2)


@dataclass(frozen=True)
class OccupancyReportDTO:
    """Resultado de `GET /admin/reports/occupancy`.

    Attributes:
        period_code: código de la ventana de matrícula sobre la que se calculó.
        generated_at: instante en que se calcularon las cifras.
        offerings: los grupos de la página pedida, del más lleno al más vacío. Se declara
            como `Sequence` porque llega tal cual desde `Page.items`, que es de solo
            lectura: copiarlo a una lista solo para cambiar el tipo daría a entender que
            alguien puede modificarla, y nadie debe.
        total: total de grupos del período, no solo los de esta página.
        page: número de página, empezando en 1.
        size: tamaño de página aplicado.
    """

    period_code: str
    generated_at: datetime
    offerings: Sequence[OfferingOccupancyDTO]
    total: int
    page: int
    size: int
