"""Casos de uso: edición del plan de estudios de un programa."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from app.application.dtos.study_plan_dto import StudyPlanDTO, StudyPlanEntryDTO
from app.application.ports.repositories.course_repository import CourseRepository
from app.application.ports.repositories.enrollment_repository import EnrollmentRepository
from app.application.ports.repositories.period_repository import PeriodRepository
from app.application.ports.repositories.program_repository import ProgramRepository
from app.application.ports.unit_of_work import UnitOfWork
from app.domain.entities.course import Course
from app.domain.entities.program import Program
from app.domain.exceptions.admin import (
    CourseRequiredByOthersError,
    RequirementWouldTrapEnrolledError,
)
from app.domain.exceptions.catalog import CourseNotFoundError, ProgramNotFoundError
from app.domain.services.requirement_graph import RequirementGraph
from app.domain.value_objects.requirement_type import RequirementType

Clock = Callable[[], datetime]


def _reloj_del_sistema() -> datetime:
    """Hora actual en UTC. Se separa para poder sustituirla en los tests."""
    return datetime.now(UTC)


class GetProgramStudyPlanUseCase:
    """Devuelve el plan de estudios de un programa cualquiera, para administración.

    Se distingue de `GetStudyPlanUseCase` en QUIÉN elige el programa, y esa diferencia es una
    regla de autorización, no un detalle. Allí el programa sale del token y no puede elegirse:
    un estudiante que pudiera pasar el identificador de otra carrera vería —y la interfaz le
    ofrecería— materias que no puede inscribir. Aquí lo elige quien administra, que tiene que
    poder editar cualquiera, y por eso este caso de uso vive tras `require_admin`.

    NO trae el semáforo. Aquel cruza el plan con el historial y la matrícula de una persona
    concreta, y aquí no hay persona: se está editando la carrera, no consultando el avance de
    nadie.
    """

    def __init__(
        self, program_repository: ProgramRepository, course_repository: CourseRepository
    ) -> None:
        self._programs = program_repository
        self._courses = course_repository

    def execute(self, program_id: UUID) -> StudyPlanDTO:
        """Compone el plan del programa indicado.

        Args:
            program_id: programa cuyo plan se consulta.

        Returns:
            El plan completo, ordenado por semestre y luego por código.

        Raises:
            ProgramNotFoundError: si el programa no existe.
        """
        programa = self._resolver_programa(program_id)

        plan = self._courses.find_study_plan(program_id)
        # Una sola consulta para todo el plan, no una por materia: un plan de diez semestres
        # son cincuenta materias, y cincuenta viajes a la base para pintar una pantalla.
        requisitos = self._courses.find_requirements_for_courses(
            [materia.id for materia, _, _ in plan], program_id
        )

        entradas = [
            StudyPlanEntryDTO(
                course=materia,
                suggested_semester=semestre,
                is_mandatory=obligatoria,
                requirements=requisitos.get(materia.id, []),
            )
            for materia, semestre, obligatoria in plan
        ]

        return StudyPlanDTO(
            program_id=programa.id,
            program_code=programa.code,
            program_name=programa.name,
            total_semesters=programa.total_semesters,
            entries=entradas,
            total_credits=sum(e.course.credits for e in entradas),
        )

    def _resolver_programa(self, program_id: UUID) -> Program:
        programa = self._programs.find_by_id(program_id)

        if programa is None:
            raise ProgramNotFoundError(program_id)

        return programa


class SetPlanCourseUseCase:
    """Añade una materia al plan de un programa, o cambia sus datos si ya estaba.

    ES UNA SOLA OPERACIÓN Y NO DOS —«añadir» y «editar»— porque la clave de `program_courses` es
    la pareja `(programa, materia)`: una materia está en el plan o no está, y si está solo puede
    estar una vez. Separarlas obligaría a quien administra a saber de antemano cuál de las dos
    pedir, y a la interfaz a consultarlo antes de cada guardado para acertar.
    """

    def __init__(
        self,
        program_repository: ProgramRepository,
        course_repository: CourseRepository,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._programs = program_repository
        self._courses = course_repository
        self._uow = unit_of_work

    def execute(
        self,
        *,
        program_id: UUID,
        course_id: UUID,
        suggested_semester: int,
        is_mandatory: bool,
    ) -> None:
        """Deja la materia en el plan con esos datos.

        Args:
            program_id: programa cuyo plan se edita.
            course_id: materia que entra en el plan.
            suggested_semester: semestre en que el plan la sugiere. Es una SUGERENCIA y no una
                restricción: quien decide si alguien puede inscribirla son los prerrequisitos.
            is_mandatory: si es obligatoria para graduarse o electiva.

        Raises:
            ProgramNotFoundError: si el programa no existe.
            CourseNotFoundError: si la materia no existe.
        """
        with self._uow:
            # Las dos comprobaciones existen porque las claves foráneas fallarían con un error
            # de integridad —y un 500— en vez de decir qué identificador está mal.
            if self._programs.find_by_id(program_id) is None:
                raise ProgramNotFoundError(program_id)

            if self._courses.find_by_id(course_id) is None:
                raise CourseNotFoundError(course_id)

            self._courses.save_plan_entry(
                program_id=program_id,
                course_id=course_id,
                suggested_semester=suggested_semester,
                is_mandatory=is_mandatory,
            )
            self._uow.commit()


class RemovePlanCourseUseCase:
    """Saca una materia del plan de un programa.

    SE RECHAZA SI OTRA MATERIA DEL PLAN LA EXIGE, y esa comprobación es la razón de ser de este
    caso de uso. La clave foránea de `program_course_requirements` apunta a `program_courses` con
    `ON DELETE CASCADE`, así que sacar `MAT101` del plan borraría en silencio el requisito
    «`MAT102` exige `MAT101`». Nadie se enteraría hasta que un estudiante inscribiera Cálculo II
    sin haber visto Cálculo I.

    Es la misma decisión que tomó la iteración 6.2.1 al cancelar una inscripción: cuando borrar
    algo dejaría a otra cosa sin lo que necesita, se rechaza nombrando quién depende, en vez de
    dejar que la base arrastre la consecuencia sin decirlo.
    """

    def __init__(self, course_repository: CourseRepository, unit_of_work: UnitOfWork) -> None:
        self._courses = course_repository
        self._uow = unit_of_work

    def execute(self, *, program_id: UUID, course_id: UUID) -> None:
        """Retira la materia del plan.

        Args:
            program_id: programa cuyo plan se edita.
            course_id: materia que sale.

        Raises:
            CourseNotFoundError: si la materia no estaba en ese plan.
            CourseRequiredByOthersError: si otra materia del plan la exige. La salida es quitar
                antes ese requisito.
        """
        with self._uow:
            dependientes = self._courses.find_requirement_dependents(course_id, program_id)

            if dependientes:
                raise CourseRequiredByOthersError(
                    course_id=course_id,
                    required_by=sorted(m.code.value for m in dependientes),
                )

            if not self._courses.remove_plan_entry(program_id=program_id, course_id=course_id):
                # No estaba en el plan. Se responde como «no existe» y no en silencio: quien
                # pidió quitarla creía que estaba, y confirmar una operación que no hizo nada
                # esconde el malentendido.
                raise CourseNotFoundError(course_id)

            self._uow.commit()


class SetRequirementUseCase:
    """Carga un requisito en el plan de un programa, o le cambia el tipo si ya estaba.

    LOS REQUISITOS SON RETROACTIVOS, y esa es la decisión que gobierna este caso de uso. No se
    versiona el plan de estudios. La razón está en cómo se leen los dos tipos de requisito, no
    en una preferencia:

    - Los **prerrequisitos** se validan SOLO al inscribir. Creada la inscripción, nadie vuelve a
      comprobarlos, así que una regla nueva no puede romper una matrícula existente.
    - Los **correquisitos** se recalculan en cada lectura de las inscripciones del estudiante, y
      solo del período ACTIVO. Ahí está el único cambio con víctima posible.

    De ahí sale la única restricción que hace falta, y no es «prohibir los cambios». Con la
    ventana ABIERTA, quien ya está inscrito ve el pendiente en su lista y lo resuelve
    inscribiendo lo que falta: el aviso ya existe y llega solo, sin depender del canal de la
    fase 10. Con la ventana CERRADA ve que le falta algo y no puede inscribir nada. Ese caso —y
    solo ese— se rechaza.

    También se rechaza el requisito que cerraría un **ciclo imposible**, que es un error mucho
    más silencioso: la base acepta cada fila por separado y las materias del ciclo quedan
    ininscribibles para siempre sin que nada avise.
    """

    def __init__(
        self,
        program_repository: ProgramRepository,
        course_repository: CourseRepository,
        enrollment_repository: EnrollmentRepository,
        period_repository: PeriodRepository,
        unit_of_work: UnitOfWork,
        clock: Clock | None = None,
    ) -> None:
        self._programs = program_repository
        self._courses = course_repository
        self._enrollments = enrollment_repository
        self._periods = period_repository
        self._uow = unit_of_work
        self._clock = clock or _reloj_del_sistema

    def execute(
        self,
        *,
        program_id: UUID,
        course_id: UUID,
        required_course_id: UUID,
        requirement_type: RequirementType,
    ) -> None:
        """Deja el requisito cargado y devuelve el plan completo.

        Args:
            program_id: plan en el que rige.
            course_id: materia que impone el requisito.
            required_course_id: materia exigida.
            requirement_type: aprobada antes, o cursada a la vez.

        Raises:
            ProgramNotFoundError: si el programa no existe.
            CourseNotFoundError: si alguna de las dos materias no está EN ESE PLAN. Se comprueba
                aquí y no se deja a la clave foránea compuesta porque el error más probable al
                cargar un plan es exigir una materia de otra carrera, y un fallo de restricción
                no dice cuál de las dos falta.
            ImpossibleRequirementCycleError: si cerraría un ciclo que nadie podría cumplir.
            RequirementWouldTrapEnrolledError: si es un correquisito que dejaría incompletas
                matrículas vivas con la ventana ya cerrada.
        """
        with self._uow:
            self._resolver_programa(program_id)
            plan = {
                materia.id: materia for materia, _, _ in self._courses.find_study_plan(program_id)
            }

            materia = plan.get(course_id)
            exigida = plan.get(required_course_id)

            if materia is None:
                raise CourseNotFoundError(course_id)

            if exigida is None:
                raise CourseNotFoundError(required_course_id)

            RequirementGraph.ensure_satisfiable(
                course=materia,
                required=exigida,
                requirement_type=requirement_type,
                existing=self._courses.find_requirements_for_courses(list(plan), program_id),
            )

            if requirement_type is RequirementType.COREQUISITE:
                self._rechazar_si_atrapa(
                    course_id=course_id, program_id=program_id, exigida=exigida
                )

            self._courses.save_requirement(
                program_id=program_id,
                course_id=course_id,
                required_course_id=required_course_id,
                requirement_type=requirement_type,
            )
            self._uow.commit()

    def _rechazar_si_atrapa(self, *, course_id: UUID, program_id: UUID, exigida: Course) -> None:
        """Impide dejar sin salida a quien ya está inscrito.

        Solo mira el período ACTIVO porque solo ese se relee: de los períodos pasados queda el
        historial de aprobadas, contra el que los correquisitos no se recalculan nunca.
        """
        periodo = self._periods.find_active()

        if periodo is None or periodo.is_open(self._clock()):
            # Sin período activo no hay matrícula viva que romper; con la ventana abierta, quien
            # esté inscrito ve el pendiente y lo resuelve él mismo.
            return

        matriculados = self._enrollments.count_active_in_program(
            course_id=course_id, program_id=program_id, enrollment_period_id=periodo.id
        )

        if matriculados > 0:
            raise RequirementWouldTrapEnrolledError(
                course_id=course_id,
                required_code=exigida.code.value,
                enrolled_count=matriculados,
            )

    def _resolver_programa(self, program_id: UUID) -> Program:
        programa = self._programs.find_by_id(program_id)

        if programa is None:
            raise ProgramNotFoundError(program_id)

        return programa


class RemoveRequirementUseCase:
    """Retira un requisito del plan.

    Quitar SIEMPRE se permite, sin la comprobación de matriculados que sí tiene añadir. No es una
    omisión: relajar una regla no puede dejar a nadie incompleto. Quien ya cumplía el requisito
    sigue cumpliendo el plan, y quien no lo cumplía deja de estar bloqueado. Un cambio que solo
    puede desatascar no necesita defensa.
    """

    def __init__(self, course_repository: CourseRepository, unit_of_work: UnitOfWork) -> None:
        self._courses = course_repository
        self._uow = unit_of_work

    def execute(self, *, program_id: UUID, course_id: UUID, required_course_id: UUID) -> None:
        """Quita el requisito del plan.

        Raises:
            CourseNotFoundError: si ese requisito no estaba cargado. Confirmar una operación que
                no hizo nada esconde el malentendido de quien la pidió.
        """
        with self._uow:
            quitado = self._courses.remove_requirement(
                program_id=program_id,
                course_id=course_id,
                required_course_id=required_course_id,
            )

            if not quitado:
                raise CourseNotFoundError(required_course_id)

            self._uow.commit()
