"""Caso de uso: consultar el horario armado del estudiante."""

from __future__ import annotations

from uuid import UUID

from app.application.dtos.enrollment_dto import ScheduleBlockDTO, StudentScheduleDTO
from app.application.ports.repositories.course_repository import CourseRepository
from app.application.ports.repositories.enrollment_repository import EnrollmentReader
from app.application.ports.repositories.offering_repository import OfferingRepository
from app.application.ports.repositories.period_repository import PeriodRepository
from app.domain.exceptions.catalog import NoActivePeriodError


class GetStudentScheduleUseCase:
    """Compone el horario del estudiante en el período activo.

    Depende de `EnrollmentReader` y no del repositorio completo (`ARCHITECTURE.md` sección 5,
    principio I). No es purismo: este caso de uso solo lee, y declararlo así deja escrito que
    no puede escribir nada. Quien construya un doble para probarlo tampoco tendrá que
    implementar un `save` que jamás se llama.

    Resuelve el horario en **tres consultas fijas** —las inscripciones activas, sus grupos, y
    las materias de esos grupos—, nunca una por inscripción.
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

    def execute(self, student_id: UUID) -> StudentScheduleDTO:
        """Devuelve el horario del estudiante en el período vigente.

        Args:
            student_id: estudiante cuyo horario se consulta. Sale del token, nunca de la
                petición: nadie puede pedir el horario de otro.

        Returns:
            El horario, con sus franjas ordenadas por día y hora. Va vacío si no tiene nada
            inscrito, que es un resultado legítimo y no un error.

        Raises:
            NoActivePeriodError: si no hay ventana de matrícula activa. Sin período no hay
                semestre al que referir el horario.
        """
        periodo = self._periods.find_active()

        if periodo is None:
            raise NoActivePeriodError()

        activas = self._enrollments.find_active_by_student(student_id, periodo.id)

        if not activas:
            return StudentScheduleDTO(academic_period=periodo.academic_period, blocks=[])

        grupos = self._offerings.find_by_ids([e.course_offering_id for e in activas])
        materias = self._courses.find_by_ids([g.course_id for g in grupos])

        franjas = [
            ScheduleBlockDTO(
                course_code=materia.code.value,
                course_name=materia.name,
                group_number=grupo.group_number,
                professor=grupo.professor.full_name if grupo.professor is not None else None,
                day_of_week=franja.day_of_week,
                start_time=franja.start_time,
                end_time=franja.end_time,
                classroom=franja.classroom,
            )
            for grupo in grupos
            if (materia := materias.get(grupo.course_id)) is not None
            for franja in grupo.schedule
        ]

        # Ordenado por día y hora: es como se lee un horario. El repositorio ya devuelve las
        # franjas de cada grupo ordenadas, pero aquí se mezclan las de varios grupos.
        franjas.sort(key=lambda f: (f.day_of_week, f.start_time))

        return StudentScheduleDTO(academic_period=periodo.academic_period, blocks=franjas)
