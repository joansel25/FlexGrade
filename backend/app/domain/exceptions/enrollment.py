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
