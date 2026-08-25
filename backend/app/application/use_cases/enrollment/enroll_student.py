"""Caso de uso: inscribir a un estudiante en un grupo.

Es la operación más sensible del sistema y la razón de ser del proyecto: durante la ventana de
matrícula, miles de estudiantes compiten por los mismos cupos en cuestión de minutos.

CÓMO SE IMPIDE EL SOBRECUPO. Tres defensas, en capas, y ninguna sustituye a las otras:

1. `CourseOffering.reserve_slot()` comprueba la capacidad sobre el grupo recién leído. Es la
   regla del dominio, y descarta el caso obvio —el grupo ya estaba lleno cuando se consultó—
   sin gastar una escritura.
2. `OfferingRepository.try_reserve_slot()` la vuelve a comprobar **de forma atómica**, en la
   misma sentencia que descuenta el cupo. Aquí se resuelve la carrera real: PostgreSQL
   serializa el acceso a la fila, así que cada transacción evalúa la capacidad contra el valor
   que la anterior acaba de escribir.
3. `CHECK (enrolled_count <= total_capacity)` en PostgreSQL. Es la red final: aunque las dos
   anteriores fallaran por un defecto de código, la base rechaza la fila.

POR QUÉ NO HAY REINTENTOS. El diseño original de `DATA_MODEL.md` proponía bloqueo optimista por
versión con reintentos acotados. Se implementó tal cual, se midió con hilos reales, y no
escalaba: con N transacciones sobre la misma fila solo una gana por ronda, así que harían falta
hasta N reintentos. Con 40 concurrentes y 100 cupos libres solo entraban 10, es decir, a 30
personas se les rechazaba un cupo que existía. Condicionar la escritura por
`enrolled_count < total_capacity` elimina el problema de raíz y hace innecesario reintentar:
nadie es rechazado sin motivo y cada intento es un solo viaje a la base de datos. La decisión
está documentada en `DATA_MODEL.md`, y los tests de `test_enrollment_concurrency.py` la
sostienen.
"""

from __future__ import annotations

from uuid import UUID

from app.application.dtos.enrollment_dto import EnrollmentDTO
from app.application.ports.cache_service import CacheService
from app.application.ports.repositories.academic_history_repository import AcademicHistoryReader
from app.application.ports.repositories.course_repository import CourseRepository
from app.application.ports.repositories.enrollment_repository import EnrollmentRepository
from app.application.ports.repositories.offering_repository import OfferingRepository
from app.application.ports.repositories.period_repository import PeriodRepository
from app.application.ports.repositories.student_repository import StudentRepository
from app.application.ports.unit_of_work import UnitOfWork
from app.application.use_cases.catalog import catalog_cache
from app.domain.entities.course_offering import CourseOffering
from app.domain.entities.course_requirement import CourseRequirement
from app.domain.entities.enrollment import Enrollment
from app.domain.entities.enrollment_period import EnrollmentPeriod
from app.domain.exceptions.authentication import StudentProfileNotFoundError
from app.domain.exceptions.catalog import CourseNotFoundError, OfferingNotFoundError
from app.domain.exceptions.enrollment import (
    AlreadyEnrolledError,
    CapacityExceededError,
    CourseNotInProgramError,
    EnrollmentPeriodInactiveError,
)
from app.domain.services.corequisite_validator import CorequisiteValidator
from app.domain.services.prerequisite_validator import PrerequisiteValidator
from app.domain.services.schedule_conflict_detector import ScheduleConflictDetector


class EnrollStudentUseCase:
    """Inscribe a un estudiante en un grupo, sin permitir sobrecupo.

    Orquesta, no decide. Cada regla vive donde le corresponde y este caso de uso solo las
    encadena (`ARCHITECTURE.md` sección 5, principio S):

    - `EnrollmentPeriod` sabe si la ventana está abierta.
    - `CourseOffering` encapsula la invariante de cupo.
    - `PrerequisiteValidator` decide si faltan materias por aprobar.
    - `CorequisiteValidator` decide si faltan materias por inscribir a la vez.
    - `ScheduleConflictDetector` decide si el horario choca.

    Así, este caso de uso tiene una única razón para cambiar: que cambie el flujo. Si mañana se
    endurece la regla de prerrequisitos, se toca el validador y nada más.
    """

    def __init__(
        self,
        enrollment_repository: EnrollmentRepository,
        offering_repository: OfferingRepository,
        period_repository: PeriodRepository,
        course_repository: CourseRepository,
        student_repository: StudentRepository,
        academic_history: AcademicHistoryReader,
        unit_of_work: UnitOfWork,
        cache: CacheService,
        prerequisite_validator: PrerequisiteValidator | None = None,
        corequisite_validator: CorequisiteValidator | None = None,
        schedule_conflict_detector: ScheduleConflictDetector | None = None,
    ) -> None:
        self._enrollment_repository = enrollment_repository
        self._offering_repository = offering_repository
        self._period_repository = period_repository
        self._course_repository = course_repository
        self._student_repository = student_repository
        self._academic_history = academic_history
        self._uow = unit_of_work
        self._cache = cache
        # Los servicios de dominio no tienen estado ni dependencias, así que se construyen
        # aquí por defecto. Se admiten por parámetro para poder sustituirlos en un test que
        # quiera aislar el flujo de las reglas.
        self._prerequisites = prerequisite_validator or PrerequisiteValidator()
        self._corequisites = corequisite_validator or CorequisiteValidator()
        self._schedule = schedule_conflict_detector or ScheduleConflictDetector()

    def execute(self, *, student_id: UUID, course_offering_id: UUID) -> EnrollmentDTO:
        """Inscribe al estudiante en el grupo indicado.

        Args:
            student_id: estudiante que se inscribe. Sale siempre del token, nunca de la
                petición: aceptarlo del cliente permitiría inscribir a cualquier otro.
            course_offering_id: grupo elegido.

        Returns:
            Los datos de la inscripción creada.

        Raises:
            EnrollmentPeriodInactiveError: si no hay ventana de matrícula abierta.
            OfferingNotFoundError: si el grupo no existe.
            CourseNotFoundError: si la materia del grupo no existe.
            AlreadyEnrolledError: si el estudiante ya está inscrito en ese grupo.
            CourseNotInProgramError: si la materia no está en su plan de estudios.
            PrerequisitesNotMetError: si le faltan materias por aprobar.
            CorequisitesNotMetError: si le faltan correquisitos por inscribir en este período.
            ScheduleConflictError: si el horario choca con otra inscripción activa.
            CapacityExceededError: si el grupo se llenó.
        """
        periodo = self._periodo_abierto()

        return self._inscribir(
            student_id=student_id,
            course_offering_id=course_offering_id,
            periodo=periodo,
        )

    # ------------------------------------------------------------------ interno

    def _periodo_abierto(self) -> EnrollmentPeriod:
        """Devuelve la ventana de matrícula vigente, o falla.

        Se comprueba antes de abrir la transacción: no depende del estado del grupo, y
        resolverlo fuera acorta el tiempo que la transacción crítica mantiene la fila tomada.
        """
        periodo = self._period_repository.find_active()

        if periodo is None:
            raise EnrollmentPeriodInactiveError()

        return periodo

    def _inscribir(
        self,
        *,
        student_id: UUID,
        course_offering_id: UUID,
        periodo: EnrollmentPeriod,
    ) -> EnrollmentDTO:
        """Ejecuta la inscripción completa dentro de una única transacción."""
        with self._uow:
            grupo = self._offering_repository.find_by_id(course_offering_id)

            if grupo is None:
                raise OfferingNotFoundError(course_offering_id)

            if grupo.enrollment_period_id != periodo.id:
                # El grupo pertenece a un semestre que ya cerró. Se rechaza como período
                # inactivo y no como grupo inexistente: el grupo existe, lo que no está
                # abierto es su ventana.
                raise EnrollmentPeriodInactiveError(
                    "Este grupo pertenece a un período de matrícula que no está abierto"
                )

            inscripcion = self._preparar_inscripcion(
                student_id=student_id, grupo=grupo, periodo_id=periodo.id
            )

            # Las reglas académicas van ANTES de tocar el cupo. El orden importa: descontar y
            # revertir por una validación fallida sería trabajo desperdiciado en la operación
            # más disputada del sistema, y durante ese instante el cupo aparecería ocupado ante
            # cualquier otra petición.
            self._validar_reglas_academicas(
                student_id=student_id, grupo=grupo, periodo_id=periodo.id
            )

            # La regla del dominio, sobre el grupo tal como se leyó. Falla de inmediato si ya
            # estaba lleno, sin gastar una escritura.
            grupo.reserve_slot()

            # Y la comprobación que de verdad decide, atómica y contra el estado actual de la
            # fila. Devuelve `False` si el grupo se llenó entre la lectura y este momento, que
            # es exactamente la carrera por el último cupo.
            if not self._offering_repository.try_reserve_slot(grupo.id):
                raise CapacityExceededError(grupo.id, grupo.total_capacity, grupo.total_capacity)

            self._enrollment_repository.save(inscripcion)
            self._uow.commit()

        # La caché del grupo se invalida FUERA de la transacción y solo tras confirmarla:
        # borrarla antes dejaría a la siguiente petición releyendo un estado que aún podría
        # revertirse. Es lo que pide `BEST_PRACTICES.md` sección 9.
        self._cache.delete(catalog_cache.clave_grupo(course_offering_id))

        return self._a_dto(inscripcion, grupo)

    def _validar_reglas_academicas(
        self, *, student_id: UUID, grupo: CourseOffering, periodo_id: UUID
    ) -> None:
        """Comprueba plan de estudios, prerrequisitos, correquisitos y choque de horario.

        Se validan en ese orden, de más barato a más caro: la pertenencia al plan es una
        consulta de existencia, los prerrequisitos leen el historial, y los correquisitos y el
        choque de horario exigen traer los grupos ya inscritos con sus franjas. Rechazar en el
        primer paso ahorra los siguientes.

        Los requisitos se piden UNA sola vez y se reparten aquí por tipo. Prerrequisitos y
        correquisitos viven en la misma tabla y salen de la misma consulta; pedirlos por
        separado sería un viaje de más a la base de datos dentro de la transacción más
        disputada del sistema.

        El plan del que salen los requisitos es el del ESTUDIANTE, no uno de la materia: desde
        la iteración 6.2 la misma materia puede exigir cosas distintas en dos carreras, y lo
        que obliga a esta persona es lo que diga su plan.
        """
        estudiante = self._student_repository.find_by_id(student_id)

        if estudiante is None:
            raise StudentProfileNotFoundError()

        if not self._course_repository.belongs_to_program(grupo.course_id, estudiante.program_id):
            raise CourseNotInProgramError(grupo.course_id, estudiante.program_id)

        requisitos = self._course_repository.find_requirements(
            grupo.course_id, estudiante.program_id
        )
        aprobadas = self._academic_history.find_approved_course_ids(student_id)

        self._prerequisites.validate(
            course_id=grupo.course_id,
            required=[r.course for r in requisitos if r.is_prerequisite()],
            approved_course_ids=aprobadas,
        )

        # Los grupos ya inscritos sirven para las dos comprobaciones que quedan, así que se
        # traen una sola vez: los correquisitos preguntan por sus materias, y el detector de
        # choques, por sus franjas horarias.
        inscritos = self._grupos_ya_inscritos(student_id, periodo_id)

        self._validar_correquisitos(
            grupo=grupo,
            program_id=estudiante.program_id,
            requisitos=requisitos,
            inscritos=inscritos,
            aprobadas=aprobadas,
        )

        self._schedule.ensure_no_conflict(candidate=grupo, enrolled=inscritos)

    def _validar_correquisitos(
        self,
        *,
        grupo: CourseOffering,
        program_id: UUID,
        requisitos: list[CourseRequirement],
        inscritos: list[CourseOffering],
        aprobadas: set[UUID],
    ) -> None:
        """Comprueba que se cursen a la vez las materias que esta exige cursar a la vez.

        Si la materia no tiene correquisitos se sale sin consultar nada. Es el caso de la
        inmensa mayoría, y `find_mutual_corequisites` solo tiene sentido cuando hay algo que
        comprobar: lanzarla siempre añadiría una consulta a cada inscripción del sistema para
        no responder nada.
        """
        correquisitos = [r.course for r in requisitos if r.is_corequisite()]

        if not correquisitos:
            return

        self._corequisites.validate(
            course_id=grupo.course_id,
            required=correquisitos,
            # Materias, no grupos: da igual en qué grupo se curse el correquisito.
            enrolled_course_ids={g.course_id for g in inscritos},
            approved_course_ids=aprobadas,
            mutual_course_ids=self._course_repository.find_mutual_corequisites(
                grupo.course_id, program_id
            ),
        )

    def _grupos_ya_inscritos(self, student_id: UUID, periodo_id: UUID) -> list[CourseOffering]:
        """Trae los grupos activos del estudiante con su horario resuelto.

        Dos consultas fijas —las inscripciones y después todos sus grupos de una vez—, nunca
        una por inscripción. Un N+1 aquí caería dentro de la transacción crítica, que es el
        peor sitio posible para tenerlo.
        """
        activas = self._enrollment_repository.find_active_by_student(student_id, periodo_id)

        if not activas:
            return []

        return self._offering_repository.find_by_ids([e.course_offering_id for e in activas])

    def _preparar_inscripcion(
        self, *, student_id: UUID, grupo: CourseOffering, periodo_id: UUID
    ) -> Enrollment:
        """Crea la inscripción, o reactiva la que quedó cancelada.

        La restricción `UNIQUE (student_id, course_offering_id, enrollment_period_id)` impide
        insertar una fila nueva cuando alguien cancela y vuelve a inscribirse en el mismo
        grupo. En vez de duplicar el registro —o borrarlo, perdiendo el rastro de que hubo una
        cancelación— se reactiva el existente.

        Raises:
            AlreadyEnrolledError: si la inscripción existe y sigue activa.
        """
        existente = self._enrollment_repository.find_by_student_and_offering(
            student_id, grupo.id, periodo_id
        )

        if existente is None:
            return Enrollment.create(
                student_id=student_id,
                course_offering_id=grupo.id,
                enrollment_period_id=periodo_id,
            )

        if existente.is_active():
            raise AlreadyEnrolledError(grupo.id)

        existente.reactivate()
        return existente

    def _a_dto(self, inscripcion: Enrollment, grupo: CourseOffering) -> EnrollmentDTO:
        """Compone la respuesta con los datos de la materia."""
        materia = self._course_repository.find_by_id(grupo.course_id)

        if materia is None:
            # No debería ocurrir: `course_offerings.course_id` es una clave foránea. Se
            # comprueba igualmente porque un `None` inesperado produciría un 500 opaco en vez
            # de un error que dice qué pasó.
            raise CourseNotFoundError(grupo.course_id)

        return EnrollmentDTO(
            id=inscripcion.id,
            student_id=inscripcion.student_id,
            course_offering_id=grupo.id,
            course_code=materia.code.value,
            course_name=materia.name,
            group_number=grupo.group_number,
            enrolled_at=inscripcion.enrolled_at,
            status=inscripcion.status,
        )
