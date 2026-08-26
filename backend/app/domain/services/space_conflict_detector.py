"""Servicio de dominio: un espacio no puede estar reservado dos veces a la vez."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.domain.entities.space import Space
from app.domain.exceptions.admin import SpaceCapacityExceededError, SpaceDoubleBookedError
from app.domain.value_objects.schedule_block import ScheduleBlock


@dataclass(frozen=True)
class SpaceReservation:
    """Una franja ya reservada en un espacio, con el grupo al que pertenece.

    Lleva el grupo además del horario porque es lo único que convierte el rechazo en algo
    accionable: «el aula está ocupada» deja a quien programa buscando a ciegas, y «la ocupa el
    grupo 02 de MAT101» le dice exactamente con quién hablar.

    Attributes:
        space_id: espacio ocupado.
        block: franja en la que lo está.
        course_code: código de la materia que lo ocupa.
        group_number: número del grupo que lo ocupa.
    """

    space_id: UUID
    block: ScheduleBlock
    course_code: str
    group_number: str


class SpaceConflictDetector:
    """Comprueba que un grupo quepa en sus aulas y no se las quite a nadie.

    ES LA PRIMERA DE DOS DEFENSAS, y no la que garantiza nada. La garantía la da la restricción
    de exclusión `GiST` que la migración `0010` pone sobre `schedule_blocks`: PostgreSQL rechaza
    físicamente dos franjas que se solapen en el mismo espacio, el mismo día y el mismo período,
    aunque el código que las inserte esté equivocado. Este servicio existe para lo que una
    restricción no puede dar: un mensaje que diga QUÉ ocupa el aula y a qué hora, en vez de un
    error de integridad que acabaría en un 500.

    Es el mismo reparto de papeles que impide el sobrecupo —`reserve_slot()` explica,
    `CHECK (enrolled_count <= total_capacity)` garantiza—, y por la misma razón: quitar
    cualquiera de las dos deja el sistema peor. Sin la restricción, dos peticiones simultáneas
    pueden comprobar a la vez que el aula está libre y reservarla las dos. Sin este servicio, esa
    carrera perdida se le presenta a una persona como una avería del servidor.

    NO comprueba el choque de horario del grupo consigo mismo: de eso se encarga
    `CreateCourseOfferingUseCase._verificar_horario_coherente`, que ya existía y mira otra cosa
    —dos clases del mismo grupo a la misma hora— aunque el solapamiento se calcule igual.

    Es un objeto sin estado y recibe todo por parámetro, como el resto de servicios de dominio.
    """

    def ensure_fits(self, *, space: Space, total_capacity: int) -> None:
        """Comprueba que el grupo quepa en el aula.

        Un aforo DESCONOCIDO no bloquea. `Space.fits` devuelve `None` cuando nadie ha medido el
        espacio —el caso de todos los que nacieron del traslado de textos de la 7.1— y tratar ese
        «no sé» como un «no cabe» dejaría inutilizables aulas perfectamente válidas por un dato
        que falta en el inventario, no por un problema real. Es una decisión consciente: se
        prefiere no impedir una asignación correcta a impedir una incorrecta que nadie puede
        siquiera confirmar.

        Args:
            space: el aula candidata.
            total_capacity: cupos del grupo que se quiere programar allí.

        Raises:
            SpaceCapacityExceededError: si el aforo se conoce y es insuficiente.
        """
        if space.fits(total_capacity) is False:
            # El `is False` es deliberado: `None` —aforo desconocido— no entra aquí.
            raise SpaceCapacityExceededError(
                space_code=space.code,
                capacity=space.capacity or 0,
                required=total_capacity,
            )

    def ensure_free(
        self,
        *,
        candidate: ScheduleBlock,
        reservations: list[SpaceReservation],
    ) -> None:
        """Comprueba que el aula de la franja esté libre a esa hora.

        Args:
            candidate: la franja que se quiere programar. Si no tiene aula asignada no hay nada
                que comprobar: una franja sin espacio no se lo quita a nadie.
            reservations: lo que ya está reservado en ese espacio y ese período.

        Raises:
            SpaceDoubleBookedError: si alguna reserva se solapa. Lleva el aula, el día, la hora
                y el grupo que la ocupa, porque el rechazo tiene que decir con quién chocas.
        """
        if candidate.space is None:
            return

        for reserva in reservations:
            if reserva.space_id != candidate.space.id:
                continue

            if candidate.overlaps(reserva.block):
                raise SpaceDoubleBookedError(
                    space_code=candidate.space.code,
                    day_of_week=candidate.day_of_week,
                    start_time=reserva.block.start_time.isoformat(timespec="minutes"),
                    course_code=reserva.course_code,
                    group_number=reserva.group_number,
                )
