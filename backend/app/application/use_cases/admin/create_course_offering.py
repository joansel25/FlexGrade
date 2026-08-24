"""Caso de uso: abrir un grupo de una materia en el período activo."""

from __future__ import annotations

from uuid import UUID, uuid4

from app.application.ports.repositories.course_repository import CourseRepository
from app.application.ports.repositories.offering_repository import OfferingRepository
from app.application.ports.repositories.period_repository import PeriodRepository
from app.application.ports.repositories.professor_repository import ProfessorReader
from app.application.ports.unit_of_work import UnitOfWork
from app.domain.entities.course_offering import CourseOffering
from app.domain.entities.professor import Professor
from app.domain.exceptions.admin import DuplicateOfferingGroupError, OverlappingScheduleError
from app.domain.exceptions.catalog import (
    CourseNotFoundError,
    NoActivePeriodError,
    ProfessorNotFoundError,
)
from app.domain.value_objects.schedule_block import ScheduleBlock


class CreateCourseOfferingUseCase:
    """Abre un grupo de una materia dentro de la ventana de matrícula activa.

    El período no se recibe en la petición, se toma del que esté activo (`API.md` sección 6:
    «Crea un nuevo grupo para el período activo»). Aceptarlo como parámetro permitiría crear
    grupos en un período cerrado por un identificador copiado de otro semestre, y el error solo
    se notaría cuando los estudiantes no vieran la materia.
    """

    def __init__(
        self,
        offering_repository: OfferingRepository,
        course_repository: CourseRepository,
        period_repository: PeriodRepository,
        professor_reader: ProfessorReader,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._offerings = offering_repository
        self._courses = course_repository
        self._periods = period_repository
        self._professors = professor_reader
        self._uow = unit_of_work

    def execute(
        self,
        *,
        course_id: UUID,
        group_number: str,
        total_capacity: int,
        schedule: list[ScheduleBlock],
        professor_id: UUID | None = None,
    ) -> CourseOffering:
        """Crea el grupo.

        Args:
            course_id: materia que se dicta.
            group_number: número de grupo dentro de la materia (`01`, `02`).
            total_capacity: cupos totales; tiene que ser positivo.
            schedule: franjas semanales en las que se dicta.
            professor_id: docente asignado, o `None` si aún está por asignar.

        Returns:
            El grupo creado, con cero inscritos.

        Raises:
            NoActivePeriodError: si no hay ninguna ventana de matrícula activa.
            CourseNotFoundError: si la materia no existe.
            ProfessorNotFoundError: si se indicó un docente que no existe.
            DuplicateOfferingGroupError: si ese número de grupo ya existe para la materia en
                el período activo.
            OverlappingScheduleError: si dos franjas del horario se cruzan entre sí.
        """
        self._verificar_horario_coherente(schedule)

        with self._uow:
            periodo = self._periods.find_active()

            if periodo is None:
                raise NoActivePeriodError()

            # Las tres comprobaciones existen porque las claves foráneas fallarían con un error
            # de integridad —y un 500— en vez de decir qué identificador está mal.
            if self._courses.find_by_id(course_id) is None:
                raise CourseNotFoundError(course_id)

            if professor_id is not None and not self._professors.exists(professor_id):
                raise ProfessorNotFoundError(professor_id)

            existentes = self._offerings.find_by_course_and_period(course_id, periodo.id)

            if any(o.group_number == group_number for o in existentes):
                raise DuplicateOfferingGroupError(course_id, group_number)

            grupo = CourseOffering(
                id=uuid4(),
                enrollment_period_id=periodo.id,
                course_id=course_id,
                group_number=group_number,
                total_capacity=total_capacity,
                enrolled_count=0,
                version=0,
                # Solo el identificador importa para persistir; el nombre lo resuelve el
                # repositorio cuando alguien consulte el grupo. Construir aquí un `Professor`
                # de relleno evita tener que arrastrar el identificador suelto por la entidad.
                professor=(
                    None if professor_id is None else Professor(id=professor_id, full_name="")
                ),
                schedule=tuple(schedule),
            )

            self._offerings.save(grupo)
            self._uow.commit()

        # Se relee para devolver el grupo con su docente resuelto, tal como lo entrega el
        # catálogo. Es una consulta más, pero ocurre una vez por grupo creado —no durante el
        # pico— y evita que esta respuesta tenga una forma distinta de la de `GET /offerings`.
        creado = self._offerings.find_by_id(grupo.id)

        return creado if creado is not None else grupo

    @staticmethod
    def _verificar_horario_coherente(schedule: list[ScheduleBlock]) -> None:
        """Comprueba que las franjas del grupo no se crucen entre sí.

        Se hace fuera de la transacción: no depende de nada persistido y fallar antes de
        abrirla ahorra una conexión a la base de datos.

        Raises:
            OverlappingScheduleError: si dos franjas se solapan.
        """
        for indice, franja in enumerate(schedule):
            for otra in schedule[indice + 1 :]:
                if franja.overlaps(otra):
                    raise OverlappingScheduleError(
                        franja.day_of_week, franja.start_time.isoformat()
                    )
