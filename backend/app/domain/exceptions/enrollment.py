"""Errores del dominio de inscripción.

Todos se traducen a `409 Conflict` salvo `CourseNotInProgramError`, que es `403` (`API.md`
sección 4). El 409 es el código correcto para casi todos: no es que la petición esté mal
formada —un 400— ni que falte permiso, sino que **el estado actual del sistema** impide la
operación. El mismo cuerpo enviado cinco minutos antes habría funcionado.

Cada excepción lleva en `details` lo que el cliente necesita para explicar el fallo sin tener
que interpretar el mensaje: qué prerrequisitos faltan, con qué materia choca el horario,
cuántos cupos hay. Ese bloque viaja tal cual dentro de la respuesta.
"""

from __future__ import annotations

from uuid import UUID

from app.domain.exceptions.base import DomainError


class EnrollmentPeriodInactiveError(DomainError):
    """No hay ventana de matrícula abierta en este momento.

    Cubre los dos casos por igual —que no exista período activo y que exista pero esté fuera
    de sus fechas— porque para quien intenta inscribirse significan lo mismo: ahora no se
    puede. La distinción sí importa en `GET /enrollment-periods/current`, que la expone con
    `is_active` e `is_open`.
    """

    def __init__(self, message: str = "No hay un período de matrícula abierto") -> None:
        super().__init__(message)


class CapacityExceededError(DomainError):
    """El grupo llegó a su cupo máximo.

    Es el error que reciben los 99 estudiantes que pierden la carrera por el último cupo. Se
    lanza desde `CourseOffering.reserve_slot()`, dentro de la entidad, para que la regla viva
    en un solo sitio.
    """

    def __init__(self, offering_id: UUID, total_capacity: int, enrolled_count: int) -> None:
        super().__init__(
            "El grupo no tiene cupos disponibles",
            details={
                "offering_id": str(offering_id),
                "capacity": total_capacity,
                "enrolled": enrolled_count,
            },
        )


class AlreadyEnrolledError(DomainError):
    """El estudiante ya está inscrito en ese grupo en el período vigente."""

    def __init__(self, offering_id: UUID) -> None:
        super().__init__(
            "Ya estás inscrito en este grupo",
            details={"offering_id": str(offering_id)},
        )


class AlreadyEnrolledInCourseError(DomainError):
    """El estudiante ya cursa esta materia en otro grupo del período vigente.

    **Separada de `AlreadyEnrolledError` a propósito**, aunque las dos digan «ya estás
    inscrito». Se corrigen de forma distinta: la otra no exige hacer nada —ya está donde
    quería— y esta obliga a cancelar el grupo que ya tiene antes de poder tomar este. Un solo
    código para las dos dejaría a la persona sin saber cuál de las dos situaciones es la suya.

    Lleva el grupo que ya ocupa en `details` para que la interfaz pueda nombrarlo: «ya estás en
    el grupo 01» es accionable, «ya cursas esta materia» obliga a ir a buscarlo.
    """

    def __init__(self, course_id: UUID, enrolled_offering_id: UUID, group_number: str) -> None:
        super().__init__(
            "Ya estás cursando esta materia en otro grupo",
            details={
                "course_id": str(course_id),
                "enrolled_offering_id": str(enrolled_offering_id),
                "enrolled_group_number": group_number,
            },
        )


class PrerequisitesNotMetError(DomainError):
    """Faltan materias prerrequisito por aprobar.

    Lleva en `details` los códigos que faltan, no solo un aviso genérico: el estudiante
    necesita saber **qué** le falta para poder hacer algo al respecto.
    """

    def __init__(self, course_id: UUID, missing: list[str]) -> None:
        super().__init__(
            "No has aprobado los prerrequisitos de esta materia",
            details={"course_id": str(course_id), "missing_prerequisites": missing},
        )


class CorequisitesNotMetError(DomainError):
    """Faltan materias correquisito por inscribir en este mismo período.

    Se distingue de `PrerequisitesNotMetError` con un código propio y no comparte el suyo
    porque lo que hay que hacer al recibirlos es distinto: ante un prerrequisito que falta no
    se puede hacer nada hoy —hay que aprobarlo en otro semestre—, mientras que un correquisito
    que falta se resuelve inscribiendo la otra materia a continuación. Un solo código
    obligaría a la interfaz a adivinar cuál de las dos cosas decir.
    """

    def __init__(self, course_id: UUID, missing: list[str]) -> None:
        super().__init__(
            "Debes inscribir al mismo tiempo las materias correquisito",
            details={"course_id": str(course_id), "missing_corequisites": missing},
        )


class CorequisiteDependencyError(DomainError):
    """No se puede cancelar: otra materia inscrita exige cursar esta a la vez.

    Es el correquisito visto desde el otro lado. Sin esta comprobación, la cancelación sería
    una puerta trasera a un estado que la inscripción nunca habría aceptado: quien inscribe
    `FIS101` con `MAT101` puede después cancelar `MAT101` y quedarse cursando Física sin el
    Cálculo que la regla exige.

    Lleva en `details` los códigos de las materias que dependen de esta, porque la acción que
    resuelve el bloqueo es concreta —cancelar antes esas— y sin nombrarlas la persona no puede
    hacer nada.
    """

    def __init__(self, course_id: UUID, dependents: list[str]) -> None:
        super().__init__(
            "Otra materia que tienes inscrita exige cursar esta al mismo tiempo",
            details={"course_id": str(course_id), "required_by": dependents},
        )


class ScheduleConflictError(DomainError):
    """El horario del grupo choca con otra inscripción activa.

    Identifica el grupo con el que choca y el día y la hora del cruce, para que la interfaz
    pueda señalarlo en el horario en vez de limitarse a rechazar la operación.
    """

    def __init__(self, conflicting_offering_id: UUID, day_of_week: int, start_time: str) -> None:
        super().__init__(
            "El horario de este grupo choca con otra materia que ya tienes inscrita",
            details={
                "conflicting_offering_id": str(conflicting_offering_id),
                "day_of_week": day_of_week,
                "start_time": start_time,
            },
        )


class CourseNotInProgramError(DomainError):
    """La materia no pertenece al plan de estudios del programa del estudiante.

    Es el único de este módulo que se traduce a `403` y no a `409`: no es un conflicto con el
    estado del sistema, sino una operación que a esta persona no le corresponde hacer.
    """

    def __init__(self, course_id: UUID, program_id: UUID) -> None:
        super().__init__(
            "Esta materia no pertenece a tu plan de estudios",
            details={"course_id": str(course_id), "program_id": str(program_id)},
        )


class EnrollmentNotFoundError(DomainError):
    """La inscripción solicitada no existe.

    Se usa también cuando la inscripción existe pero pertenece a otro estudiante. Es
    deliberado: responder «no es tuya» confirmaría que ese identificador corresponde a una
    inscripción real y permitiría enumerarlas probando identificadores.
    """

    def __init__(self, enrollment_id: UUID) -> None:
        super().__init__(
            "La inscripción solicitada no existe",
            details={"enrollment_id": str(enrollment_id)},
        )


class EnrollmentAlreadyCancelledError(DomainError):
    """La inscripción ya estaba cancelada.

    Cancelar dos veces liberaría el cupo dos veces, y el segundo `release_slot()` dejaría
    `enrolled_count` por debajo de la ocupación real: un cupo fantasma que dos personas
    podrían tomar.
    """

    def __init__(self, enrollment_id: UUID) -> None:
        super().__init__(
            "Esta inscripción ya fue cancelada",
            details={"enrollment_id": str(enrollment_id)},
        )


class StudentNotEnrolledError(DomainError):
    """Ese estudiante no aparece en ese grupo.

    No se reutiliza `EnrollmentNotFoundError` porque aquel habla de una inscripción por su
    identificador, y aquí lo que se conoce son dos: el estudiante y el grupo. Devolver el
    primero obligaría a inventar un identificador que nadie tiene, y el mensaje diría que no
    existe algo que quien pregunta nunca nombró.
    """

    def __init__(self, *, student_id: UUID, offering_id: UUID) -> None:
        super().__init__(
            "Ese estudiante no está inscrito en este grupo",
            details={"student_id": str(student_id), "offering_id": str(offering_id)},
        )


class CannotGradeCancelledEnrollmentError(DomainError):
    """Se intentó calificar una inscripción cancelada.

    Una materia que se dio de baja no se cursó, así que no hay nada que calificar. Y no es un
    detalle formal: la nota que se guardara aquí viajaría a `academic_history` en la
    consolidación de la 9.3 como si la materia se hubiera cursado, y contaría —o dejaría de
    contar— como prerrequisito.

    Ocurre de verdad: alguien cancela después de que el docente descargue la lista, y al subir
    las notas la fila sigue en su copia.
    """

    def __init__(self, enrollment_id: UUID) -> None:
        super().__init__(
            "Esa inscripción está cancelada, así que no hay materia que calificar",
            details={"enrollment_id": str(enrollment_id)},
        )


class OfferingNotAssignedError(DomainError):
    """El grupo existe, pero no lo dicta quien intenta calificarlo.

    Es 403 y no 404: decir que no existe cuando sí existe manda a buscar un error de tecleo
    donde el problema es de permiso. Un docente que ve este mensaje sabe que tiene que hablar
    con Registro Académico, no revisar la URL.
    """

    def __init__(self, offering_id: UUID) -> None:
        super().__init__(
            "Ese grupo no está entre los que dictas",
            details={"offering_id": str(offering_id)},
        )


class GradingPeriodClosedError(DomainError):
    """El grupo pertenece a un período que ya no es el activo.

    Las notas de un semestre cerrado son historia: cambiarlas recalcularía prerrequisitos que ya
    se usaron para matricular, y alguien podría estar cursando ahora mismo una materia que
    dejaría de poder cursar.
    """

    def __init__(self, offering_id: UUID) -> None:
        super().__init__(
            "Ese grupo es de un período que ya no está activo, y sus notas ya no se cambian",
            details={"offering_id": str(offering_id)},
        )
