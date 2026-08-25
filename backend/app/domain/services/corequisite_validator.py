"""Servicio de dominio: validación de correquisitos."""

from __future__ import annotations

from uuid import UUID

from app.domain.entities.course import Course
from app.domain.exceptions.enrollment import CorequisiteDependencyError, CorequisitesNotMetError


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
    crítica del sistema para resolver un caso que el bloque ya resuelve. La contrapartida es que
    entre la primera inscripción del bloque y la segunda la matrícula queda incompleta, y por
    eso `ListStudentEnrollmentsUseCase` calcula los correquisitos pendientes de cada materia
    inscrita: el estado intermedio se permite, pero no se esconde.

    Cubre las dos caras de la regla —`validate` al inscribir y `resolve_cancellation` al
    cancelar— y no se parte en dos clases a propósito: son la misma regla mirada desde cada
    lado, y separarlas dejaría que una cambiara sin la otra. Es justo lo que pasó entre la
    iteración 6.2 y esta: la inscripción respetaba los correquisitos y la cancelación no, así
    que bastaba con cancelar la materia exigida para quedar en un estado que inscribir jamás
    habría permitido.

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

    def resolve_cancellation(
        self,
        *,
        course_id: UUID,
        dependents: list[Course],
        enrolled_course_ids: set[UUID],
        mutual_course_ids: set[UUID],
    ) -> set[UUID]:
        """Decide qué hay que cancelar junto con esta materia, o si no se puede cancelar.

        LA CANCELACIÓN TAMBIÉN TIENE QUE RESPETAR LA REGLA, y no es evidente: inscribir y
        cancelar parecen operaciones independientes, pero sin esta comprobación cancelar sería
        una puerta trasera al estado que la inscripción rechaza. Quien inscribe `FIS101` con
        `MAT101` a la vez podría cancelar `MAT101` justo después y quedarse cursando Física sin
        el Cálculo que la regla exige, sin que nada lo impidiera.

        La decisión se reparte en dos según la dirección del requisito, por el mismo motivo por
        el que `validate` exime a los pares mutuos:

        - **Dependencia en un solo sentido** (`FIS101` exige `MAT101`, y `MAT101` no exige
          nada): cancelar `MAT101` se RECHAZA mientras `FIS101` siga inscrita. El orden correcto
          existe y la persona puede seguirlo: cancela primero la que depende.
        - **Dependencia mutua** (`FIS101` y `FIS102` se exigen entre sí): rechazar dejaría las
          dos imposibles de cancelar para siempre, que es el mismo bloqueo circular de la
          inscripción con el signo cambiado. Se cancela el BLOQUE ENTERO. Es coherente con cómo
          entró: si el bloque se cursa como una unidad, se abandona como una unidad.

        Args:
            course_id: materia cuya inscripción se quiere cancelar.
            dependents: materias del plan que exigen a `course_id` como correquisito suyo.
            enrolled_course_ids: materias que el estudiante tiene activas en el período. Solo
                importan las inscritas: una dependencia que no está cursando no le afecta.
            mutual_course_ids: materias que forman bloque mutuo con `course_id`.

        Returns:
            Los identificadores de las materias que hay que cancelar junto con esta. Vacío
            cuando la cancelación no arrastra nada.

        Raises:
            CorequisiteDependencyError: si alguna materia inscrita depende de esta en un solo
                sentido. Lleva sus códigos, porque la salida es cancelarlas antes.
        """
        activos = [materia for materia in dependents if materia.id in enrolled_course_ids]

        bloqueantes = [
            materia.code.value for materia in activos if materia.id not in mutual_course_ids
        ]

        if bloqueantes:
            raise CorequisiteDependencyError(course_id, sorted(bloqueantes))

        return {materia.id for materia in activos}
