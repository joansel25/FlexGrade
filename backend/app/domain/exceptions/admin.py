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


class DuplicateSpaceCodeError(DomainError):
    """Ya existe un espacio con ese código.

    El código se compara NORMALIZADO —mayúsculas, sin espacios—, así que `a-201` choca con
    `A-201`. Sin esa normalización volvería el problema que la iteración 7.1 vino a resolver:
    dos filas para el mismo salón, y una restricción de doble reserva incapaz de impedir nada
    porque cree que son sitios distintos.
    """

    def __init__(self, code: str) -> None:
        super().__init__(
            f"Ya existe un espacio con el código '{code}'",
            details={"code": code},
        )


class CourseRequiredByOthersError(DomainError):
    """No se puede sacar la materia del plan: otras del mismo plan la exigen.

    La clave foránea de `program_course_requirements` apunta a `program_courses` con
    `ON DELETE CASCADE`, así que sacarla borraría en silencio los requisitos que la nombran.
    Nadie se enteraría hasta que un estudiante inscribiera la materia que dependía de ella.

    Lleva los códigos de las que dependen porque la salida es concreta —quitar antes ese
    requisito— y sin nombrarlas no hay forma de saber cuál.
    """

    def __init__(self, *, course_id: UUID, required_by: list[str]) -> None:
        super().__init__(
            "Otras materias del plan exigen esta, así que no se puede quitar todavía",
            details={"course_id": str(course_id), "required_by": required_by},
        )


class SpaceDoubleBookedError(DomainError):
    """El aula ya está ocupada por otro grupo a esa hora.

    Es la cara legible de la restricción de exclusión que impide el estado. Lleva el grupo que
    la ocupa además del día y la hora, porque «el aula está ocupada» deja a quien programa
    buscando a ciegas y «la ocupa el grupo 02 de MAT101» le dice con quién hablar.
    """

    def __init__(
        self,
        *,
        space_code: str,
        day_of_week: int,
        start_time: str,
        course_code: str,
        group_number: str,
    ) -> None:
        super().__init__(
            f"El aula {space_code} ya está ocupada a esa hora",
            details={
                "space_code": space_code,
                "day_of_week": day_of_week,
                "start_time": start_time,
                "occupied_by": {"course_code": course_code, "group_number": group_number},
            },
        )


class SpaceCapacityExceededError(DomainError):
    """El grupo no cabe en el aula.

    Solo se lanza cuando el aforo se CONOCE. Un espacio sin aforo medido no bloquea nada: los
    que nacieron del traslado de textos de la 7.1 no traían el dato, y tratar ese «no sé» como
    un «no cabe» inutilizaría aulas válidas por una laguna del inventario.
    """

    def __init__(self, *, space_code: str, capacity: int, required: int) -> None:
        super().__init__(
            f"El aula {space_code} tiene aforo para {capacity} y el grupo es de {required}",
            details={"space_code": space_code, "capacity": capacity, "required": required},
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


class ImpossibleRequirementCycleError(DomainError):
    """El requisito cerraría un ciclo que ninguna materia del ciclo podría satisfacer.

    `MAT101` exige `MAT102` como prerrequisito y `MAT102` exige `MAT101`: para inscribir la
    primera hay que haber aprobado la segunda, y para aprobar la segunda hay que haber inscrito
    la primera. Las dos quedan ininscribibles para siempre, y nada avisa: la base acepta cada
    fila por separado, el validador las rechaza una a una sin poder decir por qué, y el semáforo
    las pinta bloqueadas sin salida. El error aparece meses después, cuando un estudiante se
    queda atascado.

    Un ciclo de PUROS correquisitos no es un error: «`FIS101` y `LAB101` se cursan juntas» es la
    forma normal de decir que dos materias van en bloque, y la iteración 6.2 construyó la
    exención de pares mutuos que lo hace inscribible. Lo que no se puede satisfacer es la mezcla.

    Lleva la vuelta completa porque «hay un ciclo» no dice cuál de las aristas sobra.
    """

    def __init__(self, *, cycle: list[str]) -> None:
        super().__init__(
            "Ese requisito dejaría un ciclo que ninguna de las materias podría cumplir: "
            + " → ".join(cycle),
            details={"cycle": cycle},
        )


class RequirementWouldTrapEnrolledError(DomainError):
    """Añadir el correquisito dejaría incompletas matrículas que ya nadie puede arreglar.

    Los requisitos son RETROACTIVOS por decisión de la iteración 8.3, y en casi todos los casos
    eso no hace daño: los prerrequisitos solo se validan al inscribir, así que una regla nueva
    no puede romper una matrícula existente. Los correquisitos sí se recalculan en cada lectura,
    y ahí aparece el único caso con víctima.

    La diferencia la marca la ventana. Con la ventana ABIERTA, quien ya está inscrito ve el
    pendiente en su lista de inscripciones y lo resuelve inscribiendo la materia que falta: el
    aviso ya existe y llega solo. Con la ventana CERRADA ve que le falta algo y no puede
    inscribir nada. Queda atrapado, y ninguna operación del sistema lo desatasca.

    Por eso se rechaza solo en ese caso, y no siempre: prohibirlo también con la ventana abierta
    impediría corregir un plan justo cuando todavía se puede corregir sin coste.

    Lleva a cuántos afectaría porque la salida es una decisión —esperar a la siguiente ventana, o
    abrir esta— y el número es lo que permite tomarla.
    """

    def __init__(self, *, course_id: UUID, required_code: str, enrolled_count: int) -> None:
        super().__init__(
            f"Hay {enrolled_count} matriculados en esta materia y la ventana está cerrada: "
            f"añadir '{required_code}' como correquisito los dejaría incompletos sin que puedan "
            "inscribirlo",
            details={
                "course_id": str(course_id),
                "required_code": required_code,
                "enrolled_count": enrolled_count,
            },
        )
