"""Caso de uso: el expediente académico del estudiante (iteración 9.4)."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from itertools import groupby
from uuid import UUID

from app.application.dtos.academic_history_dto import (
    AcademicHistoryDTO,
    HistoryEntryDTO,
    HistoryPeriodDTO,
)
from app.application.ports.repositories.academic_history_repository import AcademicHistoryReader
from app.application.ports.repositories.course_repository import CourseRepository
from app.domain.entities.academic_record import AcademicRecord
from app.domain.entities.course import Course
from app.domain.entities.student import Student
from app.domain.value_objects.history_status import HistoryStatus

CERO = Decimal("0.00")


class GetAcademicHistoryUseCase:
    """Compone el expediente académico de quien pregunta.

    Cierra el círculo visible de la Fase 9: hasta ahora el semáforo decía «aprobada» sin que el
    estudiante pudiera ver dónde ni con qué nota. Lo que la 9.3 escribe, esto lo devuelve.

    **El estudiante sale del token, nunca de la ruta.** El expediente es el dato más sensible que
    guarda el sistema —notas, materias perdidas, cuántas veces se repitió algo— y una ruta con
    identificador dentro permitiría leer el de cualquiera. No hay parámetro con el que pedir otro
    porque no existe tal parámetro.

    **Muestra lo perdido igual que lo aprobado.** Un expediente que oculta lo reprobado no es un
    expediente, y la materia repetida aparece las dos veces: las dos ocurrieron.
    """

    def __init__(
        self, academic_history: AcademicHistoryReader, course_repository: CourseRepository
    ) -> None:
        self._history = academic_history
        self._courses = course_repository

    def execute(self, student: Student) -> AcademicHistoryDTO:
        """Devuelve el expediente agrupado por semestre.

        Args:
            student: perfil ya resuelto desde el token.

        Returns:
            Los semestres del más reciente al más antiguo, con su promedio, más el acumulado.
            Un expediente vacío es una respuesta legítima: quien acaba de ingresar todavía no ha
            cerrado ningún semestre.
        """
        registros = self._history.find_by_student(student.id)

        if not registros:
            return AcademicHistoryDTO(
                student_code=student.student_code.value, full_name=student.full_name
            )

        # Una sola consulta para todas las materias del expediente: pedirlas por semestre serían
        # diez viajes a la base para pintar una pantalla.
        materias = self._courses.find_by_ids([r.course_id for r in registros])

        periodos = [
            self._componer_periodo(semestre, list(filas), materias)
            # `groupby` exige que la entrada venga ordenada, y el repositorio ya la devuelve por
            # semestre descendente. Reordenar aquí duplicaría un criterio que ya tiene dueño.
            for semestre, filas in groupby(registros, key=lambda r: r.academic_period)
        ]

        return AcademicHistoryDTO(
            student_code=student.student_code.value,
            full_name=student.full_name,
            periods=periodos,
            total_credits_approved=sum(p.credits_approved for p in periodos),
            cumulative_average=self._promedio(registros, materias),
        )

    def _componer_periodo(
        self,
        academic_period: str,
        registros: list[AcademicRecord],
        materias: dict[UUID, Course],
    ) -> HistoryPeriodDTO:
        """Arma un semestre con sus materias y sus cifras."""
        entradas = [
            HistoryEntryDTO(
                course=materias[registro.course_id],
                final_grade=registro.final_grade,
                status=registro.status,
            )
            for registro in registros
            # Una materia que ya no está en el catálogo no se puede pintar sin nombre. Se omite
            # en vez de mostrar una fila anónima, que no le diría nada a quien la lee.
            if registro.course_id in materias
        ]

        return HistoryPeriodDTO(
            academic_period=academic_period,
            entries=sorted(entradas, key=lambda e: e.course.code.value),
            credits_attempted=sum(e.course.credits for e in entradas),
            credits_approved=sum(
                e.course.credits for e in entradas if e.status is HistoryStatus.APPROVED
            ),
            average=self._promedio(registros, materias),
        )

    @staticmethod
    def _promedio(registros: list[AcademicRecord], materias: dict[UUID, Course]) -> Decimal:
        """Promedio PONDERADO POR CRÉDITOS.

        Una materia de cuatro créditos pesa el doble que una de dos, que es como se calcula en
        cualquier institución. Una media simple daría un número que no coincide con el
        certificado oficial, y quien lo viera lo tomaría por bueno.

        Las retiradas (`WITHDRAWN`) no cuentan: no se cursaron hasta el final, así que no tienen
        nota que promediar. Hoy ninguna operación las produce, pero la regla se escribe aquí para
        que el día que existan no haya que recordar añadirla.
        """
        creditos = 0
        puntos = Decimal(0)

        for registro in registros:
            materia = materias.get(registro.course_id)

            if materia is None or registro.status is HistoryStatus.WITHDRAWN:
                continue

            creditos += materia.credits
            puntos += registro.final_grade.value * materia.credits

        if creditos == 0:
            return CERO

        # HALF_UP, igual que `Grade`: el redondeo bancario es correcto para promediar dinero y
        # equivocado cuando el número decide si alguien conserva una beca.
        return (puntos / creditos).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
