"""Servicio de dominio: validación de correquisitos."""

from __future__ import annotations

from uuid import UUID

from app.domain.entities.course import Course
from app.domain.exceptions.enrollment import CorequisitesNotMetError


class CorequisiteValidator:
    """Comprueba que el estudiante curse a la vez lo que la materia exige a la vez.

    Un correquisito NO es un prerrequisito escrito de otra forma. El prerrequisito se resuelve
    contra el historial académico, que es un hecho cerrado; el correquisito se resuelve contra
    la matrícula que la persona está armando **en este mismo momento**, y por eso su validación
    tiene dos particularidades que el otro no tiene.

    PRIMERA: se cumple de tres maneras. La materia exigida vale si está inscrita y activa en
    el período vigente, y también si el estudiante ya la aprobó en un semestre anterior. Lo
    segundo puede parecer una concesión y no lo es: quien exige cursar `MAT101` junto a
    `FIS101` lo hace para que tenga las herramientas de cálculo mientras ve física, y alguien
    que ya la aprobó las tiene con más motivo. Rechazarlo obligaría a repetir una materia
    aprobada.

    SEGUNDA: el correquisito puede ser MUTUO, y ahí aparece un bloqueo que el prerrequisito no
    puede producir. Si `FIS101` exige `FIS102` y `FIS102` exige `FIS101`, inscribirlas de una
    en una es imposible: la primera de las dos siempre encuentra a la otra sin inscribir. Un
    prerrequisito circular es un error de datos que se corrige; un correquisito circular es lo
    normal —la teoría y su laboratorio se cursan juntos— y tiene que funcionar.

    La salida es validar el CONJUNTO en vez de la materia suelta: las materias unidas por
    correquisitos mutuos forman un bloque que se cursa entero, y cualquiera de ellas puede ser
    la primera en entrar. Por eso este validador recibe `mutual_course_ids` y no exige que esas
    estén ya inscritas. La alternativa era un endpoint de inscripción múltiple que aceptara el
    bloque en una sola transacción; se descartó porque cambia el contrato de la operación más
    crítica del sistema para resolver un caso que el bloque ya resuelve. La contrapartida está
    dicha: entre la primera inscripción del bloque y la segunda, la matrícula queda incompleta,
    y es la semaforización del plan (iteración 6.3) la que tiene que hacerlo visible.

    Como el resto de servicios de dominio, no consulta nada: recibe todo por parámetro y su
    única razón para cambiar es que cambie la regla de correquisitos.
    """

    def validate(
        self,
        *,
        course_id: UUID,
        required: list[Course],
        enrolled_course_ids: set[UUID],
        approved_course_ids: set[UUID],
        mutual_course_ids: set[UUID],
    ) -> None:
        """Verifica que no falte ningún correquisito.

        Args:
            course_id: materia que se quiere inscribir.
            required: correquisitos directos de esa materia en el plan del estudiante.
            enrolled_course_ids: materias que el estudiante tiene inscritas y activas en el
                período vigente. Se recibe como conjunto de materias, no de grupos: da igual
                en qué grupo curse el correquisito, lo que importa es que lo curse.
            approved_course_ids: materias que ya aprobó. Satisfacen el correquisito por sí
                solas: quien ya la aprobó no tiene que volver a cursarla.
            mutual_course_ids: materias que exigen a `course_id` como correquisito suyo, es
                decir, las que forman bloque con ella. No se les exige estar inscritas: son
                justo las que producirían el bloqueo circular.

        Raises:
            CorequisitesNotMetError: si falta alguno. Lleva los **códigos** de las materias
                que faltan, porque la respuesta útil aquí es «inscribe también MAT101», y para
                eso hay que decir cuál.
        """
        faltantes = [
            materia.code.value
            for materia in required
            if materia.id not in enrolled_course_ids
            and materia.id not in approved_course_ids
            and materia.id not in mutual_course_ids
        ]

        if faltantes:
            # Ordenados, por la misma razón que en los prerrequisitos: un orden que depende de
            # la consulta hace que la misma petición dé dos respuestas distintas y vuelve
            # imposible probar el mensaje.
            raise CorequisitesNotMetError(course_id, sorted(faltantes))
