"""Caso de uso: cerrar un período y llevar sus notas al historial (iteración 9.3)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from app.application.dtos.consolidation_dto import ConsolidationDTO
from app.application.ports.repositories.academic_history_repository import AcademicHistoryReader
from app.application.ports.repositories.course_repository import CourseRepository
from app.application.ports.repositories.enrollment_repository import EnrollmentRepository
from app.application.ports.repositories.offering_repository import OfferingRepository
from app.application.ports.repositories.period_repository import PeriodRepository
from app.application.ports.unit_of_work import UnitOfWork
from app.domain.entities.academic_record import AcademicRecord
from app.domain.exceptions.admin import (
    AlreadyInAcademicHistoryError,
    InconsistentConsolidationError,
    PeriodHasUngradedEnrollmentsError,
    PeriodStillOpenError,
)
from app.domain.exceptions.catalog import PeriodNotFoundError
from app.domain.value_objects.history_status import HistoryStatus

Clock = Callable[[], datetime]


def _reloj_del_sistema() -> datetime:
    """Hora actual en UTC. Se separa para poder sustituirla en los tests."""
    return datetime.now(UTC)


class ConsolidatePeriodUseCase:
    """Cierra el semestre: convierte las notas del período en historial académico.

    **ES LA OPERACIÓN QUE CIERRA EL CICLO Y LA ÚNICA IRREVERSIBLE DEL SISTEMA.** Hasta la Fase 9,
    `academic_history` solo la escribía el seed: en producción habría quedado vacía para siempre,
    `find_approved_course_ids` habría devuelto vacío y nadie habría cumplido ningún prerrequisito
    a partir del segundo semestre. El sistema funcionaba un solo semestre de su vida.

    Por ser irreversible, **todo se comprueba antes de escribir nada**. Los cuatro rechazos:

    1. **El período ya se consolidó.** Repetirlo duplicaría el expediente.
    2. **La ventana sigue abierta.** Escribiría el expediente de un semestre en el que todavía
       entra gente; quien se matriculara después no aparecería en el historial y nadie se
       enteraría hasta que le faltara un prerrequisito años más tarde.
    3. **Quedan inscripciones sin nota.** No hay valor razonable con el que rellenarlas: un cero
       reprobaría a alguien por un trámite pendiente y omitirlas dejaría el expediente
       incompleto en silencio.
    4. **Alguna materia ya consta en ese semestre.** Pasa cuando dos ventanas comparten
       `academic_period` y alguien cursó lo mismo en las dos.

    **Todo ocurre en una transacción.** Un cierre a medias dejaría estudiantes con medio
    expediente, y los prerrequisitos se cumplirían o no según la materia: el peor fallo posible,
    porque no se parece a un fallo. El `UNIQUE (student_id, course_id, academic_period)` es la
    red final, con la misma filosofía de dos defensas que impide el sobrecupo.

    Las inscripciones CANCELADAS no viajan. Quien dio de baja la materia no la cursó, y llevarla
    al expediente diría que sí.
    """

    def __init__(
        self,
        period_repository: PeriodRepository,
        enrollment_repository: EnrollmentRepository,
        offering_repository: OfferingRepository,
        course_repository: CourseRepository,
        academic_history: AcademicHistoryReader,
        unit_of_work: UnitOfWork,
        clock: Clock | None = None,
    ) -> None:
        self._periods = period_repository
        self._enrollments = enrollment_repository
        self._offerings = offering_repository
        self._courses = course_repository
        self._history = academic_history
        self._uow = unit_of_work
        self._clock = clock or _reloj_del_sistema

    def execute(self, period_id: UUID) -> ConsolidationDTO:
        """Consolida el período y devuelve el resumen de lo escrito.

        Args:
            period_id: ventana de matrícula que se cierra.

        Returns:
            Cuántos registros se escribieron y cuántos aprobaron, que es lo que permite
            confirmar de un vistazo que el cierre hizo lo que se esperaba.

        Raises:
            PeriodNotFoundError: si el período no existe.
            PeriodAlreadyConsolidatedError: si ya se cerró. La lanza la entidad.
            PeriodStillOpenError: si la ventana sigue admitiendo inscripciones.
            PeriodHasUngradedEnrollmentsError: si quedan notas por poner.
            AlreadyInAcademicHistoryError: si alguna materia ya consta en ese semestre.
        """
        ahora = self._clock()

        with self._uow:
            periodo = self._periods.find_by_id(period_id)

            if periodo is None:
                raise PeriodNotFoundError(period_id)

            # Primero lo que la entidad sabe de sí misma: si ya está consolidado, no hay nada
            # más que mirar.
            if periodo.esta_consolidado():
                periodo.consolidate(now=ahora)  # lanza PeriodAlreadyConsolidatedError

            if periodo.is_open(ahora):
                raise PeriodStillOpenError(periodo.id, periodo.ends_at)

            self._rechazar_si_falta_calificar(periodo.id)

            registros = self._componer_registros(
                period_id=periodo.id, academic_period=periodo.academic_period
            )

            self._history.save_all(registros)
            periodo.consolidate(now=ahora)
            self._periods.save(periodo)

            self._uow.commit()

        return ConsolidationDTO(
            period_id=periodo.id,
            period_code=periodo.code,
            academic_period=periodo.academic_period,
            consolidated_at=ahora,
            records=len(registros),
            approved=sum(1 for r in registros if r.status is HistoryStatus.APPROVED),
        )

    def _rechazar_si_falta_calificar(self, period_id: UUID) -> None:
        """Impide consolidar con notas pendientes, nombrando los grupos que faltan."""
        pendientes = self._enrollments.count_ungraded(period_id)

        if pendientes == 0:
            return

        grupos = self._offerings.find_by_ids(self._enrollments.find_ungraded_offerings(period_id))
        materias = self._courses.find_by_ids([g.course_id for g in grupos])

        # Se nombran por materia y grupo, no por identificador: quien consolida tiene que ir a
        # hablar con esos docentes, y un UUID no le dice a cuál.
        codigos = sorted(
            f"{materias[g.course_id].code.value}-{g.group_number}"
            for g in grupos
            if g.course_id in materias
        )

        raise PeriodHasUngradedEnrollmentsError(
            period_id=period_id, pending=pendientes, offerings=codigos
        )

    def _componer_registros(self, *, period_id: UUID, academic_period: str) -> list[AcademicRecord]:
        """Traduce las inscripciones calificadas a filas del expediente.

        El expediente guarda la MATERIA, no el grupo: años después, a quien lee un historial le
        da igual con qué docente se vio Cálculo I. Por eso hay que resolver los grupos.
        """
        inscripciones = self._enrollments.find_graded_in_period(period_id)

        if not inscripciones:
            return []

        grupos = {
            g.id: g
            for g in self._offerings.find_by_ids([i.course_offering_id for i in inscripciones])
        }

        registros: list[AcademicRecord] = []

        for inscripcion in inscripciones:
            grupo = grupos.get(inscripcion.course_offering_id)
            nota = inscripcion.final_grade

            if grupo is None or nota is None:
                # Ninguno de los dos debería ocurrir: la consulta filtra por nota no nula y los
                # grupos salen de las propias inscripciones. Si ocurre, es un dato roto, y
                # saltárselo en silencio escribiría un expediente incompleto sin avisar.
                raise InconsistentConsolidationError(enrollment_id=inscripcion.id)

            registros.append(
                AcademicRecord.consolidate(
                    student_id=inscripcion.student_id,
                    course_id=grupo.course_id,
                    academic_period=academic_period,
                    final_grade=nota,
                )
            )

        self._rechazar_si_ya_constan(registros, academic_period)

        return registros

    def _rechazar_si_ya_constan(
        self, registros: list[AcademicRecord], academic_period: str
    ) -> None:
        """Comprueba los choques antes de escribir, por los DOS caminos posibles.

        El `UNIQUE` los rechazaría igualmente, pero un error de restricción en mitad de una
        transacción que escribe miles de filas no dice cuál de todas la rompió.

        Se miran dos cosas distintas y las dos ocurren de verdad:

        1. **Contra lo que YA está en el historial.** Dos ventanas que comparten
           `academic_period` —primera y segunda vuelta del mismo semestre— con alguien que cursó
           la misma materia en las dos.
        2. **Dentro del propio lote.** Alguien inscrito en DOS GRUPOS de la misma materia. El
           sistema lo impide al inscribir, así que solo llega hasta aquí por datos cargados por
           fuera; pero es exactamente el caso que hay que detectar antes, porque no se ve hasta
           que la transacción entera revienta.
        """
        ya_constan = self._history.find_recorded_courses(
            [r.student_id for r in registros], academic_period
        )
        vistos: set[tuple[UUID, UUID]] = set()
        repetidos: set[tuple[UUID, UUID]] = set()

        for registro in registros:
            clave = (registro.student_id, registro.course_id)

            if clave in vistos:
                repetidos.add(clave)

            vistos.add(clave)

        chocan = [
            r
            for r in registros
            if (r.student_id, r.course_id) in ya_constan or (r.student_id, r.course_id) in repetidos
        ]

        if not chocan:
            return

        materias = self._courses.find_by_ids([r.course_id for r in chocan])
        codigos = sorted(
            {materias[r.course_id].code.value for r in chocan if r.course_id in materias}
        )

        raise AlreadyInAcademicHistoryError(academic_period=academic_period, courses=codigos)
