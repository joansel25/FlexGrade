"""Servicio de dominio: detección de choques de horario."""

from __future__ import annotations

from collections.abc import Iterable

from app.domain.entities.course_offering import CourseOffering
from app.domain.exceptions.enrollment import ScheduleConflictError


class ScheduleConflictDetector:
    """Determina si un grupo choca con lo que el estudiante ya tiene inscrito.

    Es un objeto sin estado y recibe todo por parámetro, igual que `PrerequisiteValidator`: quien
    lo llama trae el grupo candidato y los grupos ya inscritos, y este servicio decide. Su única
    razón para cambiar es que cambie la regla de choque de horarios.

    No implementa la comparación de franjas: eso lo sabe hacer `ScheduleBlock.overlaps()`, que es
    donde vive esa regla y donde ya está probada franja a franja, incluido el caso de las clases
    consecutivas —una termina a las 10:00 y la siguiente empieza a las 10:00— que **no** son
    conflicto. Este servicio solo recorre las combinaciones.
    """

    def ensure_no_conflict(
        self,
        *,
        candidate: CourseOffering,
        enrolled: Iterable[CourseOffering],
    ) -> None:
        """Verifica que el grupo candidato no se solape con ninguno de los ya inscritos.

        Args:
            candidate: el grupo que se quiere inscribir.
            enrolled: los grupos en los que el estudiante ya está inscrito y activo.

        Raises:
            ScheduleConflictError: al primer solapamiento. Se informa del grupo con el que
                choca y del día y la hora del cruce, para que la interfaz pueda señalarlo en el
                horario en vez de limitarse a rechazar la operación.
        """
        for inscrito in enrolled:
            # Un grupo no choca consigo mismo. La comprobación es barata y evita un falso
            # positivo si quien llama incluyera el candidato en la lista por descuido.
            if inscrito.id == candidate.id:
                continue

            for franja_nueva in candidate.schedule:
                for franja_inscrita in inscrito.schedule:
                    if franja_nueva.overlaps(franja_inscrita):
                        raise ScheduleConflictError(
                            inscrito.id,
                            franja_nueva.day_of_week,
                            franja_nueva.start_time.isoformat(),
                        )
