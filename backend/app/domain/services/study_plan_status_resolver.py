"""Servicio de dominio: en qué estado está cada materia del plan de estudios."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from app.domain.entities.course_requirement import CourseRequirement
from app.domain.services.corequisite_validator import CorequisiteValidator
from app.domain.services.prerequisite_validator import PrerequisiteValidator
from app.domain.value_objects.course_status import CourseStatus


@dataclass(frozen=True)
class CourseStatusResult:
    """El estado de una materia y, si está bloqueada, por qué.

    Attributes:
        status: en qué punto está el estudiante respecto a esta materia.
        missing_prerequisites: códigos que le faltan por aprobar. Solo se llena con `BLOCKED`.
        missing_corequisites: códigos que tendría que cursar a la vez y que este período no
            puede cursar. Solo se llena con `BLOCKED`.
        corequisites: códigos que hay que inscribir junto a esta materia. Se llena SIEMPRE que
            existan, también cuando la materia está disponible: no es un impedimento, es una
            instrucción, y ocultarla hasta que falle sería repetir el error que arregló la 6.1.
    """

    status: CourseStatus
    missing_prerequisites: list[str] = field(default_factory=list)
    missing_corequisites: list[str] = field(default_factory=list)
    corequisites: list[str] = field(default_factory=list)


class StudyPlanStatusResolver:
    """Decide el estado de una materia cruzando plan, historial, matrícula y oferta.

    ESTE SERVICIO ES LA RAZÓN DE SER DE LA ITERACIÓN 6.3, y su valor no está en clasificar sino
    en **no volver a implementar las reglas**. Delega en `PrerequisiteValidator` y
    `CorequisiteValidator`, los mismos objetos que deciden si una inscripción se acepta. Escribir
    aquí una segunda versión de «le faltan prerrequisitos» sería cómodo y funcionaría el primer
    día; el problema llega el día que una de las dos cambie, porque entonces la pantalla dirá
    que la materia está disponible mientras el servidor la rechaza, y no habrá forma de que el
    estudiante entienda cuál de las dos miente.

    Por el mismo motivo el cálculo vive en el servidor y no en el navegador. Es la misma regla
    que decide la inscripción, y el cliente no puede tener una copia.

    EL ORDEN DE LAS COMPROBACIONES ES LA CLASIFICACIÓN. Cada materia cae en el primer estado que
    la describe, y están ordenadas de hecho consumado a posibilidad:

    1. ¿La aprobó? Entonces da igual todo lo demás.
    2. ¿La está cursando? Es un hecho del período, y manda sobre si «podría» inscribirla.
    3. ¿Le faltan prerrequisitos? Bloqueada, y se dice cuáles.
    4. ¿Algún correquisito es imposible este período? Bloqueada también: cumplir los
       prerrequisitos no basta si la materia que hay que cursar a la vez no tiene grupos.
    5. ¿Hay grupos abiertos? Si no, no se ofrece; ofrecer inscribirla llevaría a una pantalla
       vacía.
    6. En otro caso, disponible.

    Es un objeto sin estado y recibe todo por parámetro, como el resto de servicios de dominio:
    no consulta la base de datos ni conoce repositorios.
    """

    def __init__(
        self,
        prerequisite_validator: PrerequisiteValidator | None = None,
        corequisite_validator: CorequisiteValidator | None = None,
    ) -> None:
        self._prerequisites = prerequisite_validator or PrerequisiteValidator()
        self._corequisites = corequisite_validator or CorequisiteValidator()

    @staticmethod
    def mutual_blocks(
        requirements: dict[UUID, list[CourseRequirement]],
    ) -> dict[UUID, set[UUID]]:
        """Deduce qué materias forman bloque mutuo, a partir de los requisitos ya cargados.

        Dos materias forman bloque cuando se exigen como correquisito en LAS DOS direcciones.
        Es la misma definición que el autojoin de `find_mutual_corequisites`, resuelta aquí en
        memoria por una razón concreta: el semáforo clasifica el plan entero, y preguntárselo a
        la base de datos materia por materia sería una consulta por cada una —un N+1 sobre una
        pantalla que se abre de golpe— cuando el dato ya viajó en el mismo lote de requisitos.

        La consulta SQL sigue existiendo para la inscripción, que mira UNA materia y necesita la
        verdad de la base en ese instante, no un mapa cargado antes.

        Args:
            requirements: requisitos de cada materia del plan, indexados por materia.

        Returns:
            Por materia, las que forman bloque con ella. Las materias sin bloque no aparecen.
        """
        correquisitos = {
            course_id: {r.course.id for r in requisitos if r.is_corequisite()}
            for course_id, requisitos in requirements.items()
        }

        bloques = {
            course_id: {otra for otra in exigidas if course_id in correquisitos.get(otra, set())}
            for course_id, exigidas in correquisitos.items()
        }

        return {course_id: bloque for course_id, bloque in bloques.items() if bloque}

    def resolve(
        self,
        *,
        course_id: UUID,
        requirements: list[CourseRequirement],
        approved_course_ids: set[UUID],
        enrolled_course_ids: set[UUID],
        offered_course_ids: set[UUID],
        mutual_course_ids: set[UUID],
    ) -> CourseStatusResult:
        """Clasifica una materia del plan.

        Args:
            course_id: materia que se clasifica.
            requirements: sus requisitos directos en el plan del estudiante, de los dos tipos.
            approved_course_ids: materias que el estudiante tiene aprobadas.
            enrolled_course_ids: materias que cursa en el período vigente. Vacío fuera de la
                ventana de matrícula, que es un estado normal y no un error.
            offered_course_ids: materias del plan con al menos un grupo abierto este período.
            mutual_course_ids: materias que forman bloque de correquisitos mutuos con esta.

        Returns:
            El estado y, cuando está bloqueada, qué le falta.
        """
        correquisitos = [r.course for r in requirements if r.is_corequisite()]
        codigos_correquisitos = sorted(c.code.value for c in correquisitos)

        if course_id in approved_course_ids:
            return CourseStatusResult(CourseStatus.APPROVED, corequisites=codigos_correquisitos)

        if course_id in enrolled_course_ids:
            return CourseStatusResult(CourseStatus.ENROLLED, corequisites=codigos_correquisitos)

        faltan_prerrequisitos = self._prerequisites.missing(
            required=[r.course for r in requirements if r.is_prerequisite()],
            approved_course_ids=approved_course_ids,
        )

        if faltan_prerrequisitos:
            return CourseStatusResult(
                CourseStatus.BLOCKED,
                missing_prerequisites=faltan_prerrequisitos,
                corequisites=codigos_correquisitos,
            )

        # La sustitución que explica `CorequisiteValidator.missing`: al pintar el plan, un
        # correquisito que se PUEDE inscribir cuenta igual que uno ya inscrito.
        faltan_correquisitos = self._corequisites.missing(
            required=correquisitos,
            enrolled_course_ids=enrolled_course_ids | offered_course_ids,
            approved_course_ids=approved_course_ids,
            mutual_course_ids=mutual_course_ids,
        )

        if faltan_correquisitos:
            return CourseStatusResult(
                CourseStatus.BLOCKED,
                missing_corequisites=faltan_correquisitos,
                corequisites=codigos_correquisitos,
            )

        if course_id not in offered_course_ids:
            return CourseStatusResult(CourseStatus.NOT_OFFERED, corequisites=codigos_correquisitos)

        return CourseStatusResult(CourseStatus.AVAILABLE, corequisites=codigos_correquisitos)
