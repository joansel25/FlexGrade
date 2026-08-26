"""Casos de uso: edición del plan de estudios de un programa."""

from __future__ import annotations

from uuid import UUID

from app.application.dtos.study_plan_dto import StudyPlanDTO, StudyPlanEntryDTO
from app.application.ports.repositories.course_repository import CourseRepository
from app.application.ports.repositories.program_repository import ProgramRepository
from app.application.ports.unit_of_work import UnitOfWork
from app.domain.entities.program import Program
from app.domain.exceptions.admin import CourseRequiredByOthersError
from app.domain.exceptions.catalog import CourseNotFoundError, ProgramNotFoundError


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

        entradas = [
            StudyPlanEntryDTO(course=materia, suggested_semester=semestre, is_mandatory=obligatoria)
            for materia, semestre, obligatoria in self._courses.find_study_plan(program_id)
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
