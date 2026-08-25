"""Caso de uso: cancelar una inscripción y liberar el cupo.

Es la operación inversa a inscribir, y comparte con ella la misma exigencia de atomicidad: el
cambio de estado de la inscripción y la liberación del cupo ocurren en una sola transacción. Si
una se aplicara sin la otra el sistema quedaría con un cupo ocupado que nadie usa —o, peor, con
uno libre de más que dos personas podrían tomar—.

COMPARTE TAMBIÉN LAS REGLAS ACADÉMICAS, y eso no es evidente. Hasta la iteración 6.2 cancelar
era una operación sin reglas: bastaba con que la inscripción fuera tuya y estuviera activa. Con
los correquisitos deja de serlo, porque cancelar puede dejar al estudiante en un estado que
inscribir jamás habría aceptado: quien inscribe `FIS101` junto a `MAT101` —como exige la regla—
podría cancelar `MAT101` un segundo después y seguir cursando Física sin el Cálculo que la
acompaña. Una regla que solo se comprueba en una dirección no es una regla, es una sugerencia.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from app.application.dtos.enrollment_dto import CancellationDTO, CancelledEnrollmentDTO
from app.application.ports.cache_service import CacheService
from app.application.ports.repositories.course_repository import CourseRepository
from app.application.ports.repositories.enrollment_repository import EnrollmentRepository
from app.application.ports.repositories.offering_repository import OfferingRepository
from app.application.ports.repositories.student_repository import StudentRepository
from app.application.ports.unit_of_work import UnitOfWork
from app.application.use_cases.catalog import catalog_cache
from app.domain.entities.course_offering import CourseOffering
from app.domain.entities.enrollment import Enrollment
from app.domain.exceptions.authentication import StudentProfileNotFoundError
from app.domain.exceptions.enrollment import EnrollmentNotFoundError
from app.domain.services.corequisite_validator import CorequisiteValidator

Clock = Callable[[], datetime]


def _reloj_del_sistema() -> datetime:
    """Instante actual en UTC. Toda fecha del sistema viaja en UTC (`API.md`)."""
    return datetime.now(UTC)


class CancelEnrollmentUseCase:
    """Cancela una inscripción propia y devuelve su cupo al grupo.

    Puede arrastrar más de una inscripción. Cuando la materia forma un bloque de correquisitos
    MUTUOS —la teoría y su laboratorio, que se exigen entre sí— se cancela el bloque entero:
    rechazar la cancelación dejaría las dos imposibles de abandonar para siempre, y permitirla a
    secas dejaría a la otra inscrita sin lo que exige. La decisión la toma `CorequisiteValidator`
    y este caso de uso se limita a ejecutarla; el porqué está en su docstring.

    Por eso la operación devuelve **qué se canceló** en vez de nada. Que desaparezcan dos
    materias de la pantalla tras pulsar «Cancelar» en una sola es correcto, pero sin decirlo se
    lee como un fallo del sistema.
    """

    def __init__(
        self,
        enrollment_repository: EnrollmentRepository,
        offering_repository: OfferingRepository,
        course_repository: CourseRepository,
        student_repository: StudentRepository,
        unit_of_work: UnitOfWork,
        cache: CacheService,
        clock: Clock | None = None,
        corequisite_validator: CorequisiteValidator | None = None,
    ) -> None:
        self._enrollment_repository = enrollment_repository
        self._offering_repository = offering_repository
        self._course_repository = course_repository
        self._student_repository = student_repository
        self._uow = unit_of_work
        self._cache = cache
        self._clock = clock or _reloj_del_sistema
        self._corequisites = corequisite_validator or CorequisiteValidator()

    def execute(self, *, student_id: UUID, enrollment_id: UUID) -> CancellationDTO:
        """Cancela la inscripción indicada y las que formen bloque con ella.

        Args:
            student_id: quien pide la cancelación. Sale del token, nunca de la petición.
            enrollment_id: inscripción a cancelar.

        Returns:
            Las inscripciones que quedaron canceladas, empezando por la que se pidió. Son
            varias solo cuando la materia forma bloque de correquisitos mutuos.

        Raises:
            EnrollmentNotFoundError: si no existe **o si pertenece a otra persona**.
            EnrollmentAlreadyCancelledError: si ya estaba cancelada.
            StudentProfileNotFoundError: si la cuenta no tiene perfil académico.
            CorequisiteDependencyError: si otra materia inscrita exige cursar esta a la vez y
                no forma bloque mutuo con ella. La salida es cancelar antes esa otra.
        """
        with self._uow:
            inscripcion = self._enrollment_repository.find_by_id(enrollment_id)

            # Se responde lo mismo cuando no existe y cuando es de otro. Es deliberado: decir
            # «esa inscripción no es tuya» confirmaría que ese identificador corresponde a una
            # real, y permitiría enumerarlas probando identificadores hasta dar con una.
            if inscripcion is None or inscripcion.student_id != student_id:
                raise EnrollmentNotFoundError(enrollment_id)

            arrastradas = self._inscripciones_del_bloque(
                student_id=student_id, inscripcion=inscripcion
            )
            afectadas = [inscripcion, *arrastradas.values()]

            for activa in afectadas:
                self._cancelar(activa)

            canceladas = self._describir(afectadas)
            self._uow.commit()

        # Fuera de la transacción y solo tras confirmarla: invalidar antes dejaría a la
        # siguiente petición releyendo un estado que aún podría revertirse.
        for cancelada in canceladas:
            self._cache.delete(catalog_cache.clave_grupo(cancelada.course_offering_id))

        return CancellationDTO(items=canceladas)

    # ------------------------------------------------------------------ interno

    def _cancelar(self, inscripcion: Enrollment) -> None:
        """Cancela una inscripción y libera su cupo."""
        # La entidad rechaza cancelar lo ya cancelado. Es la primera de las dos defensas
        # contra liberar el cupo dos veces; la segunda es la guarda de `try_release_slot`,
        # que nunca deja el contador por debajo de cero.
        inscripcion.cancel(self._clock())

        self._offering_repository.try_release_slot(inscripcion.course_offering_id)
        self._enrollment_repository.save(inscripcion)

    def _inscripciones_del_bloque(
        self, *, student_id: UUID, inscripcion: Enrollment
    ) -> dict[UUID, Enrollment]:
        """Devuelve las demás inscripciones que hay que cancelar junto con esta.

        Sale por la vía rápida en cuanto ve que la materia no la exige nadie, que es el caso de
        casi todas: una consulta y ninguna más. Solo cuando existen dependientes se paga el
        resto —las inscripciones activas y el conjunto mutuo—, y para entonces ya se sabe que
        hacen falta.
        """
        grupo = self._offering_repository.find_by_id(inscripcion.course_offering_id)

        if grupo is None:
            # La clave foránea lo impide. Si aun así ocurriera, no hay materia sobre la que
            # razonar: se cancela la inscripción tal cual, que es lo que la persona pidió.
            return {}

        program_id = self._programa_del_estudiante(student_id)
        dependientes = self._course_repository.find_corequisite_dependents(
            grupo.course_id, program_id
        )

        if not dependientes:
            return {}

        activas = self._enrollment_repository.find_active_by_student(
            student_id, inscripcion.enrollment_period_id
        )
        # `find_by_ids` devuelve una lista; se indexa por identificador porque a partir de
        # aquí se busca, no se recorre.
        grupos = {
            g.id: g
            for g in self._offering_repository.find_by_ids(
                [e.course_offering_id for e in activas if e.id != inscripcion.id]
            )
        }
        por_materia = self._indexar_por_materia(activas, grupos)

        a_cancelar = self._corequisites.resolve_cancellation(
            course_id=grupo.course_id,
            dependents=dependientes,
            enrolled_course_ids=set(por_materia),
            mutual_course_ids=self._course_repository.find_mutual_corequisites(
                grupo.course_id, program_id
            ),
        )

        return {materia_id: por_materia[materia_id] for materia_id in a_cancelar}

    def _programa_del_estudiante(self, student_id: UUID) -> UUID:
        """Devuelve el plan de estudios contra el que se evalúan los correquisitos."""
        estudiante = self._student_repository.find_by_id(student_id)

        if estudiante is None:
            raise StudentProfileNotFoundError()

        return estudiante.program_id

    @staticmethod
    def _indexar_por_materia(
        activas: list[Enrollment], grupos: dict[UUID, CourseOffering]
    ) -> dict[UUID, Enrollment]:
        """Indexa las inscripciones activas por la MATERIA de su grupo.

        Por materia y no por grupo porque la regla de correquisitos habla de materias: da igual
        en qué grupo se curse el correquisito, lo que importa es que se curse.
        """
        por_materia: dict[UUID, Enrollment] = {}

        for activa in activas:
            grupo = grupos.get(activa.course_offering_id)

            if grupo is not None:
                por_materia[grupo.course_id] = activa

        return por_materia

    def _describir(self, canceladas: list[Enrollment]) -> list[CancelledEnrollmentDTO]:
        """Compone la descripción de lo que se canceló.

        Lleva código, nombre y grupo porque la respuesta sirve para decirle a la persona QUÉ se
        canceló, y un identificador no le dice nada.

        Dos consultas por lote, no dos por inscripción. El bloque son dos o tres materias y un
        N+1 aquí apenas se notaría, pero esto corre DENTRO de la transacción que libera cupos
        mientras otras personas compiten por ellos: cada viaje de más alarga lo que las filas
        permanecen tomadas.

        Un grupo o una materia que no se resuelvan se devuelven vacíos en vez de fallar. La
        cancelación ya está decidida, y romper la respuesta por un dato de presentación haría
        creer que no se aplicó.
        """
        grupos = {
            g.id: g
            for g in self._offering_repository.find_by_ids(
                [c.course_offering_id for c in canceladas]
            )
        }
        materias = self._course_repository.find_by_ids([g.course_id for g in grupos.values()])

        descripciones: list[CancelledEnrollmentDTO] = []

        for cancelada in canceladas:
            grupo = grupos.get(cancelada.course_offering_id)
            materia = None if grupo is None else materias.get(grupo.course_id)

            descripciones.append(
                CancelledEnrollmentDTO(
                    id=cancelada.id,
                    course_offering_id=cancelada.course_offering_id,
                    course_code="" if materia is None else materia.code.value,
                    course_name="" if materia is None else materia.name,
                    group_number="" if grupo is None else grupo.group_number,
                )
            )

        return descripciones
