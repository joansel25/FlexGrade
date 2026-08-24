"""Errores del dominio de administración académica.

Existen para que las operaciones de administración fallen con un mensaje que diga qué pasó, en
vez de con el error de restricción que devolvería PostgreSQL. Las restricciones de la base
siguen ahí y son la garantía final; estas excepciones son la primera línea, la que produce una
respuesta que alguien puede leer y corregir.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.domain.exceptions.base import DomainError


class InvalidPeriodRangeError(DomainError):
    """La ventana termina antes de empezar, o en el mismo instante."""

    def __init__(self, starts_at: datetime, ends_at: datetime) -> None:
        super().__init__(
            "La fecha de cierre debe ser posterior a la de apertura",
            details={"starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat()},
        )


class DuplicatePeriodCodeError(DomainError):
    """Ya existe una ventana de matrícula con ese código."""

    def __init__(self, code: str) -> None:
        super().__init__(
            "Ya existe un período de matrícula con ese código",
            details={"code": code},
        )


class DuplicateCourseCodeError(DomainError):
    """Ya existe una materia con ese código institucional."""

    def __init__(self, code: str) -> None:
        super().__init__(
            "Ya existe una materia con ese código",
            details={"code": code},
        )


class DuplicateOfferingGroupError(DomainError):
    """Ya existe ese número de grupo para la materia dentro del mismo período."""

    def __init__(self, course_id: UUID, group_number: str) -> None:
        super().__init__(
            "Ya existe un grupo con ese número para la materia en el período activo",
            details={"course_id": str(course_id), "group_number": group_number},
        )


class CapacityBelowEnrolledError(DomainError):
    """El cupo solicitado deja fuera a estudiantes que ya están inscritos.

    Reducir la capacidad por debajo de `enrolled_count` no expulsa a nadie: dejaría el grupo
    en un estado que el `CHECK (enrolled_count <= total_capacity)` rechaza, y con él la
    transacción entera. Se comprueba antes para poder decir cuántos hay inscritos, que es el
    número que quien administra necesita para elegir un cupo válido.
    """

    def __init__(self, offering_id: UUID, requested_capacity: int, enrolled_count: int) -> None:
        super().__init__(
            "El cupo no puede ser menor que el número de estudiantes ya inscritos",
            details={
                "offering_id": str(offering_id),
                "requested_capacity": requested_capacity,
                "enrolled_count": enrolled_count,
            },
        )


class ConcurrentOfferingUpdateError(DomainError):
    """Otra operación modificó el grupo mientras se ajustaba su cupo.

    Es el resultado de agotar los reintentos del bloqueo optimista por `version`. Aquí ese
    mecanismo sí es el adecuado —a diferencia del descuento de cupo, donde la contención es la
    norma—: dos administradores ajustando el mismo grupo a la vez es raro, y cuando ocurre es
    mejor rechazar la escritura que dejar que la segunda pise en silencio la decisión de la
    primera.
    """

    def __init__(self, offering_id: UUID) -> None:
        super().__init__(
            "El grupo fue modificado por otra operación; vuelva a intentarlo",
            details={"offering_id": str(offering_id)},
        )


class OverlappingScheduleError(DomainError):
    """Dos franjas del mismo grupo se cruzan entre sí.

    Un grupo no puede dictarse en dos sitios a la vez. Si se aceptara, el detector de choques
    de la inscripción compararía el grupo contra sí mismo sin encontrar nada raro —solo mira
    grupos distintos— y el estudiante acabaría con un horario imposible que nadie rechazó.
    """

    def __init__(self, day_of_week: int, start_time: str) -> None:
        super().__init__(
            "Dos franjas del horario del grupo se solapan",
            details={"day_of_week": day_of_week, "start_time": start_time},
        )
