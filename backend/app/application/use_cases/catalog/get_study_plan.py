"""Caso de uso: plan de estudios del programa del estudiante."""

from __future__ import annotations

from uuid import UUID

from app.application.dtos.study_plan_dto import StudyPlanDTO, StudyPlanEntryDTO
from app.application.ports.repositories.course_repository import CourseRepository
from app.application.ports.repositories.program_repository import ProgramRepository
from app.application.ports.repositories.student_repository import StudentRepository
from app.domain.exceptions.authentication import StudentProfileNotFoundError
from app.domain.exceptions.catalog import ProgramNotFoundError


class GetStudyPlanUseCase:
    """Devuelve el plan de estudios de la carrera que cursa el estudiante.

    Es la respuesta a «qué materias son las mías», y existe porque el catálogo no puede
    responderla: `GET /courses` lista TODAS las materias de la institución, y un estudiante de
    Derecho que ve Programación II acaba pulsando «Inscribir» para recibir un `403`. La
    interfaz estaba ofreciendo algo que iba a fallar.

    El programa **sale del token**, nunca de la petición. Aceptarlo como parámetro permitiría
    consultar el plan de otra carrera pasando su identificador, y con él la interfaz ofrecería
    de nuevo materias que la persona no puede inscribir.

    En la iteración 6.3 este mismo caso de uso ganará el estado de cada materia —aprobada,
    disponible, bloqueada— cruzando el historial académico con los prerrequisitos. Hoy devuelve
    el plan tal cual: es el cimiento sobre el que se apoya esa semaforización.
    """

    def __init__(
        self,
        student_repository: StudentRepository,
        program_repository: ProgramRepository,
        course_repository: CourseRepository,
    ) -> None:
        self._students = student_repository
        self._programs = program_repository
        self._courses = course_repository

    def execute(self, student_id: UUID) -> StudyPlanDTO:
        """Compone el plan de estudios del estudiante.

        Args:
            student_id: estudiante consultado. Sale del token.

        Returns:
            El plan completo, sin paginar, ordenado por semestre y luego por código.

        Raises:
            StudentProfileNotFoundError: si la cuenta no tiene perfil académico.
            ProgramNotFoundError: si el programa del estudiante ya no existe.
        """
        estudiante = self._students.find_by_id(student_id)

        if estudiante is None:
            raise StudentProfileNotFoundError()

        programa = self._programs.find_by_id(estudiante.program_id)

        if programa is None:
            raise ProgramNotFoundError(estudiante.program_id)

        entradas = [
            StudyPlanEntryDTO(course=materia, suggested_semester=semestre, is_mandatory=obligatoria)
            for materia, semestre, obligatoria in self._courses.find_study_plan(programa.id)
        ]

        return StudyPlanDTO(
            program_code=programa.code,
            program_name=programa.name,
            total_semesters=programa.total_semesters,
            entries=entradas,
            # Se suma en el servidor para que la cifra sea la misma aquí, en el comprobante y en
            # cualquier informe que la use después.
            total_credits=sum(e.course.credits for e in entradas),
        )
