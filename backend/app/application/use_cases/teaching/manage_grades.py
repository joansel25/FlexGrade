"""Casos de uso: pasar lista y calificar un grupo (iteración 9.2)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from app.application.dtos.teaching_dto import GradeEntryDTO, OfferingRosterDTO
from app.application.ports.repositories.course_repository import CourseRepository
from app.application.ports.repositories.enrollment_repository import EnrollmentRepository
from app.application.ports.repositories.offering_repository import OfferingRepository
from app.application.ports.repositories.period_repository import PeriodRepository
from app.application.ports.repositories.student_repository import StudentRepository
from app.application.ports.unit_of_work import UnitOfWork
from app.domain.entities.course_offering import CourseOffering
from app.domain.exceptions.catalog import CourseNotFoundError, OfferingNotFoundError
from app.domain.exceptions.enrollment import (
    GradingPeriodClosedError,
    OfferingNotAssignedError,
    StudentNotEnrolledError,
)
from app.domain.value_objects.grade import Grade

Clock = Callable[[], datetime]


def _reloj_del_sistema() -> datetime:
    """Hora actual en UTC. Se separa para poder sustituirla en los tests."""
    return datetime.now(UTC)


class _AccesoAlGrupo:
    """Resuelve el grupo comprobando que quien pregunta puede tocarlo.

    Vive aparte porque las dos operaciones —pasar lista y calificar— necesitan exactamente la
    misma comprobación, y duplicarla garantizaría que se separen: es el tipo de código que se
    corrige en un sitio y se olvida en el otro, dejando un endpoint abierto sin que nada falle
    de forma visible.

    **Los tres rechazos van separados a propósito.** «No existe», «no es tuyo» y «es de otro
    semestre» se arreglan en sitios distintos: revisando la URL, hablando con Registro
    Académico, o aceptando que esas notas ya son historia. Un único 404 mandaría a dos de los
    tres casos a buscar donde no está el problema.
    """

    def __init__(
        self, offering_repository: OfferingRepository, period_repository: PeriodRepository
    ) -> None:
        self._offerings = offering_repository
        self._periods = period_repository

    def resolver(self, *, offering_id: UUID, professor_id: UUID) -> CourseOffering:
        """Devuelve el grupo si el docente puede operar sobre él.

        Raises:
            OfferingNotFoundError: si el grupo no existe.
            OfferingNotAssignedError: si existe pero lo dicta otra persona.
            GradingPeriodClosedError: si pertenece a un período que ya no es el activo. Cambiar
                notas de un semestre cerrado recalcularía prerrequisitos que ya se usaron para
                matricular, y alguien podría estar cursando ahora mismo una materia que dejaría
                de poder cursar.
        """
        grupo = self._offerings.find_by_id(offering_id)

        if grupo is None:
            raise OfferingNotFoundError(offering_id)

        if grupo.professor is None or grupo.professor.id != professor_id:
            raise OfferingNotAssignedError(offering_id)

        periodo = self._periods.find_active()

        if periodo is None or grupo.enrollment_period_id != periodo.id:
            raise GradingPeriodClosedError(offering_id)

        return grupo


class GetOfferingRosterUseCase:
    """La lista del grupo: quién está inscrito y qué nota lleva.

    Es lo que hace utilizable a la 9.2. Sin ella, calificar exigiría conocer de antemano el
    identificador de cada estudiante, que no está a la vista en ningún sitio.

    Solo salen las inscripciones VIVAS. Quien canceló no cursó la materia, y ofrecerla en la
    lista invitaría a calificar una fila que el dominio va a rechazar.
    """

    def __init__(
        self,
        offering_repository: OfferingRepository,
        enrollment_repository: EnrollmentRepository,
        student_repository: StudentRepository,
        course_repository: CourseRepository,
        period_repository: PeriodRepository,
    ) -> None:
        self._acceso = _AccesoAlGrupo(offering_repository, period_repository)
        self._enrollments = enrollment_repository
        self._students = student_repository
        self._courses = course_repository

    def execute(self, *, offering_id: UUID, professor_id: UUID) -> OfferingRosterDTO:
        """Compone la lista del grupo.

        Returns:
            La lista con cada estudiante, su código y su nota si la tiene, más cuántas quedan
            por calificar: es la cifra que le dice al docente si ya terminó.
        """
        grupo = self._acceso.resolver(offering_id=offering_id, professor_id=professor_id)
        materia = self._courses.find_by_id(grupo.course_id)

        if materia is None:
            # Un grupo cuya materia no está en el catálogo es un dato roto, no un caso a
            # mostrar: la lista saldría sin decir de qué asignatura es.
            raise CourseNotFoundError(grupo.course_id)

        inscripciones = self._enrollments.find_by_offering(offering_id)
        perfiles = {
            estudiante.id: estudiante
            for estudiante in self._students.find_by_ids([i.student_id for i in inscripciones])
        }

        entradas = [
            GradeEntryDTO(
                student=perfiles[inscripcion.student_id],
                enrollment=inscripcion,
            )
            for inscripcion in inscripciones
            if inscripcion.student_id in perfiles
        ]

        return OfferingRosterDTO(
            offering=grupo,
            course=materia,
            entries=sorted(entradas, key=lambda e: e.student.full_name),
            pending=sum(1 for e in entradas if not e.enrollment.esta_calificada()),
        )


class SetGradeUseCase:
    """Registra o corrige la nota final de un estudiante en un grupo.

    **La nota se guarda en la INSCRIPCIÓN, no en `academic_history`.** El historial es un
    registro consolidado: lo que hay ahí decide prerrequisitos y aparece en el expediente.
    Escribir cada tecleo del docente directamente allí haría irreversible una corrección tan
    normal como equivocarse de fila. La nota nace como borrador y la 9.3 la consolida en una
    sola operación transaccional.

    Es idempotente: volver a poner la misma nota deja el mismo estado. Por eso el endpoint es un
    `PUT` y no un `POST`, y por eso corregir una nota mal tecleada no necesita una operación
    aparte que quien califica tenga que recordar.
    """

    def __init__(
        self,
        offering_repository: OfferingRepository,
        enrollment_repository: EnrollmentRepository,
        period_repository: PeriodRepository,
        unit_of_work: UnitOfWork,
        clock: Clock | None = None,
    ) -> None:
        self._acceso = _AccesoAlGrupo(offering_repository, period_repository)
        self._enrollments = enrollment_repository
        self._uow = unit_of_work
        self._clock = clock or _reloj_del_sistema

    def execute(
        self, *, offering_id: UUID, professor_id: UUID, student_id: UUID, grade: Grade
    ) -> None:
        """Deja la nota registrada.

        Raises:
            OfferingNotFoundError, OfferingNotAssignedError, GradingPeriodClosedError: lo que
                comprueba `_AccesoAlGrupo`.
            StudentNotEnrolledError: si ese estudiante no está en ese grupo.
            CannotGradeCancelledEnrollmentError: si canceló la materia. Se distingue del
                anterior porque son cosas distintas: una suena a error de tecleo y la otra es
                lo que de verdad pasó.
        """
        with self._uow:
            self._acceso.resolver(offering_id=offering_id, professor_id=professor_id)

            inscripcion = self._enrollments.find_by_student_and_offering_any_status(
                student_id, offering_id
            )

            if inscripcion is None:
                raise StudentNotEnrolledError(student_id=student_id, offering_id=offering_id)

            # La regla de que una cancelada no se califica vive en la ENTIDAD y no aquí: es una
            # invariante de la inscripción, y ponerla en el caso de uso dejaría la puerta
            # abierta a cualquier otro camino que escriba la nota.
            inscripcion.grade(grade, now=self._clock())

            self._enrollments.save(inscripcion)
            self._uow.commit()
