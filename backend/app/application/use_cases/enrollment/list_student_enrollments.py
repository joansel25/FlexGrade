"""Caso de uso: inscripciones activas del estudiante en el período vigente."""

from __future__ import annotations

from uuid import UUID

from app.application.dtos.enrollment_dto import (
    ScheduleBlockDTO,
    StudentEnrollmentDTO,
    StudentEnrollmentsDTO,
)
from app.application.ports.repositories.course_repository import CourseRepository
from app.application.ports.repositories.enrollment_repository import EnrollmentReader
from app.application.ports.repositories.offering_repository import OfferingRepository
from app.application.ports.repositories.period_repository import PeriodRepository
from app.domain.exceptions.catalog import NoActivePeriodError


class ListStudentEnrollmentsUseCase:
    """Lista lo que el estudiante tiene inscrito, con lo necesario para poder cancelarlo.

    Se distingue de `GetStudentScheduleUseCase` en algo más que el formato, y por eso son dos
    casos de uso y no uno con un parámetro: el horario está pensado para **leerse** —franjas
    sueltas ordenadas por día y hora, sin identidad propia— y esto para **operar** sobre las
    inscripciones. Devolver el identificador de la inscripción es justo lo que permite
    cancelarla; el horario no lo lleva porque una franja no se cancela.

    Solo devuelve las **activas**. Las canceladas no ocupan cupo, no aparecen en el horario y
    no impiden volver a inscribir el mismo grupo: mostrarlas obligaría a la interfaz a
    filtrarlas, y esa es una decisión que no debe repetirse en cada cliente.
    """

    def __init__(
        self,
        enrollment_reader: EnrollmentReader,
        offering_repository: OfferingRepository,
        course_repository: CourseRepository,
        period_repository: PeriodRepository,
    ) -> None:
        self._enrollments = enrollment_reader
        self._offerings = offering_repository
        self._courses = course_repository
        self._periods = period_repository

    def execute(self, student_id: UUID) -> StudentEnrollmentsDTO:
        """Devuelve las inscripciones activas del estudiante.

        Args:
            student_id: estudiante consultado. Sale del token, nunca de la petición: nadie
                puede ver las inscripciones de otro.

        Returns:
            Las inscripciones activas del período vigente, con sus créditos sumados. Va vacío
            si no ha inscrito nada, que es un resultado legítimo y no un error.

        Raises:
            NoActivePeriodError: si no hay ventana de matrícula activa. Sin período no hay
                semestre al que referir las inscripciones.
        """
        periodo = self._periods.find_active()

        if periodo is None:
            raise NoActivePeriodError()

        activas = self._enrollments.find_active_by_student(student_id, periodo.id)

        if not activas:
            return StudentEnrollmentsDTO(
                academic_period=periodo.academic_period,
                period_code=periodo.code,
                items=[],
                total_credits=0,
            )

        # Dos consultas por lote, no una por inscripción: el número de viajes a la base de
        # datos no depende de cuántas materias tenga inscritas el estudiante.
        grupos = {
            g.id: g for g in self._offerings.find_by_ids([e.course_offering_id for e in activas])
        }
        materias = self._courses.find_by_ids([g.course_id for g in grupos.values()])

        items: list[StudentEnrollmentDTO] = []

        for inscripcion in activas:
            grupo = grupos.get(inscripcion.course_offering_id)

            if grupo is None:
                # No debería ocurrir: la clave foránea lo impide. Se omite en vez de fallar
                # porque una inconsistencia puntual no debe dejar al estudiante sin ver el
                # resto de sus materias en plena matrícula.
                continue

            materia = materias.get(grupo.course_id)

            if materia is None:
                continue

            items.append(
                StudentEnrollmentDTO(
                    id=inscripcion.id,
                    course_offering_id=grupo.id,
                    course_id=grupo.course_id,
                    course_code=materia.code.value,
                    course_name=materia.name,
                    credits=materia.credits,
                    group_number=grupo.group_number,
                    professor=grupo.professor.full_name if grupo.professor is not None else None,
                    schedule=[
                        ScheduleBlockDTO(
                            course_code=materia.code.value,
                            course_name=materia.name,
                            group_number=grupo.group_number,
                            professor=(
                                grupo.professor.full_name if grupo.professor is not None else None
                            ),
                            day_of_week=franja.day_of_week,
                            start_time=franja.start_time,
                            end_time=franja.end_time,
                            classroom=franja.classroom,
                        )
                        for franja in grupo.schedule
                    ],
                    enrolled_at=inscripcion.enrolled_at,
                )
            )

        # Por código de materia: es el orden con el que se reconocen en un comprobante, y es
        # estable entre consultas, a diferencia del orden de inserción.
        items.sort(key=lambda i: i.course_code)

        return StudentEnrollmentsDTO(
            academic_period=periodo.academic_period,
            period_code=periodo.code,
            items=items,
            total_credits=sum(i.credits for i in items),
        )
