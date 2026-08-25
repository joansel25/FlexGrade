"""Caso de uso: plan de estudios del programa del estudiante, con su semáforo."""

from __future__ import annotations

from uuid import UUID

from app.application.dtos.study_plan_dto import StudyPlanDTO, StudyPlanEntryDTO
from app.application.ports.repositories.academic_history_repository import AcademicHistoryReader
from app.application.ports.repositories.course_repository import CourseRepository
from app.application.ports.repositories.enrollment_repository import EnrollmentReader
from app.application.ports.repositories.offering_repository import OfferingRepository
from app.application.ports.repositories.period_repository import PeriodRepository
from app.application.ports.repositories.program_repository import ProgramRepository
from app.application.ports.repositories.student_repository import StudentRepository
from app.domain.entities.course import Course
from app.domain.exceptions.authentication import StudentProfileNotFoundError
from app.domain.exceptions.catalog import ProgramNotFoundError
from app.domain.services.study_plan_status_resolver import StudyPlanStatusResolver
from app.domain.value_objects.course_status import CourseStatus


class GetStudyPlanUseCase:
    """Devuelve el plan de estudios de la carrera con el estado de cada materia.

    Es la respuesta a «qué materias son las mías», y existe porque el catálogo no puede
    responderla: `GET /courses` lista TODAS las materias de la institución, y un estudiante de
    Derecho que ve Programación II acaba pulsando «Inscribir» para recibir un `403`. La
    interfaz estaba ofreciendo algo que iba a fallar.

    Desde la iteración 6.3 responde además **en qué punto está** con cada materia: aprobada,
    cursándose, disponible, sin oferta este período o bloqueada por lo que le falte. Ese
    cálculo lo hace `StudyPlanStatusResolver` delegando en los mismos servicios de dominio que
    deciden si una inscripción se acepta, y por eso vive en el servidor: una segunda versión de
    la regla en el navegador funcionaría el primer día y discreparía el día que una de las dos
    cambiara, dejando al estudiante ante una pantalla que ofrece lo que el servidor rechaza.

    El programa **sale del token**, nunca de la petición. Aceptarlo como parámetro permitiría
    consultar el plan de otra carrera pasando su identificador, y con él la interfaz ofrecería
    de nuevo materias que la persona no puede inscribir.

    FUNCIONA FUERA DE LA VENTANA DE MATRÍCULA, y es deliberado. La pregunta que responde el
    plan —«qué me falta para graduarme»— tiene sentido todo el año, así que no hay período
    activo no es un error: significa que nada se ofrece, y las materias que cumplen requisitos
    salen como `NOT_OFFERED` en vez de como disponibles. Hacer fallar el endpoint dejaría la
    pantalla inservible durante la mayor parte del semestre.

    CUÁNTAS CONSULTAS CUESTA. Seis, y ninguna depende del tamaño del plan: estudiante,
    programa, plan, requisitos de todas las materias en lote, historial aprobado y —solo si hay
    período activo— inscripciones vigentes y oferta del período. La reciprocidad de los
    correquisitos se deduce en memoria del lote de requisitos, para no pagar una consulta por
    materia.
    """

    def __init__(
        self,
        student_repository: StudentRepository,
        program_repository: ProgramRepository,
        course_repository: CourseRepository,
        period_repository: PeriodRepository,
        offering_repository: OfferingRepository,
        enrollment_reader: EnrollmentReader,
        academic_history: AcademicHistoryReader,
        status_resolver: StudyPlanStatusResolver | None = None,
    ) -> None:
        self._students = student_repository
        self._programs = program_repository
        self._courses = course_repository
        self._periods = period_repository
        self._offerings = offering_repository
        self._enrollments = enrollment_reader
        self._academic_history = academic_history
        self._resolver = status_resolver or StudyPlanStatusResolver()

    def execute(self, student_id: UUID) -> StudyPlanDTO:
        """Compone el plan de estudios del estudiante con el estado de cada materia.

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

        plan = self._courses.find_study_plan(programa.id)
        materias = [materia for materia, _, _ in plan]

        entradas = self._clasificar(
            student_id=student_id, program_id=programa.id, plan=plan, materias=materias
        )

        return StudyPlanDTO(
            program_id=programa.id,
            program_code=programa.code,
            program_name=programa.name,
            total_semesters=programa.total_semesters,
            entries=entradas,
            # Se suman en el servidor para que las cifras sean las mismas aquí, en el
            # comprobante y en cualquier informe que las use después.
            total_credits=sum(e.course.credits for e in entradas),
            approved_credits=sum(
                e.course.credits for e in entradas if e.status is CourseStatus.APPROVED
            ),
        )

    # ------------------------------------------------------------------ interno

    def _clasificar(
        self,
        *,
        student_id: UUID,
        program_id: UUID,
        plan: list[tuple[Course, int, bool]],
        materias: list[Course],
    ) -> list[StudyPlanEntryDTO]:
        """Resuelve el estado de cada materia del plan.

        Todo lo que el resolutor necesita se trae ANTES del bucle y en lote. Es la diferencia
        entre seis consultas y seis por cada materia del plan.
        """
        ids = [materia.id for materia in materias]
        requisitos = self._courses.find_requirements_for_courses(ids, program_id)
        aprobadas = self._academic_history.find_approved_course_ids(student_id)
        inscritas, ofertadas = self._estado_del_periodo(student_id, ids)
        bloques = self._resolver.mutual_blocks(requisitos)

        entradas: list[StudyPlanEntryDTO] = []

        for materia, semestre, obligatoria in plan:
            resultado = self._resolver.resolve(
                course_id=materia.id,
                requirements=requisitos.get(materia.id, []),
                approved_course_ids=aprobadas,
                enrolled_course_ids=inscritas,
                offered_course_ids=ofertadas,
                mutual_course_ids=bloques.get(materia.id, set()),
            )

            entradas.append(
                StudyPlanEntryDTO(
                    course=materia,
                    suggested_semester=semestre,
                    is_mandatory=obligatoria,
                    status=resultado.status,
                    missing_prerequisites=resultado.missing_prerequisites,
                    missing_corequisites=resultado.missing_corequisites,
                    corequisites=resultado.corequisites,
                )
            )

        return entradas

    def _estado_del_periodo(
        self, student_id: UUID, course_ids: list[UUID]
    ) -> tuple[set[UUID], set[UUID]]:
        """Devuelve qué materias cursa el estudiante y cuáles se ofrecen en el período vigente.

        Sin período activo devuelve dos conjuntos vacíos en vez de fallar. No es un caso de
        error: durante la mayor parte del semestre no hay ventana abierta, y el plan sigue
        respondiendo «qué me falta para graduarme». Con los conjuntos vacíos, lo que cumple
        requisitos sale como `NOT_OFFERED`, que es exactamente lo cierto.
        """
        periodo = self._periods.find_active()

        if periodo is None:
            return set(), set()

        activas = self._enrollments.find_active_by_student(student_id, periodo.id)
        grupos = self._offerings.find_by_ids([e.course_offering_id for e in activas])

        return (
            {grupo.course_id for grupo in grupos},
            self._offerings.find_course_ids_offered_in(course_ids, periodo.id),
        )
