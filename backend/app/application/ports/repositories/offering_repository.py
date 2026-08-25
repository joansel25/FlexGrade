"""Puerto de persistencia del agregado CourseOffering."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from app.domain.entities.course_offering import CourseOffering


class OfferingRepository(ABC):
    """Contrato de acceso a los grupos de una materia.

    Todos los métodos devuelven el grupo **completo**: con su docente y sus franjas de
    horario ya resueltos. El adaptador es responsable de hacerlo en una sola consulta; un
    caso de uso nunca debe recorrer una lista de grupos pidiendo sus horarios uno a uno.
    """

    @abstractmethod
    def find_by_id(self, offering_id: UUID) -> CourseOffering | None:
        """Recupera un grupo por su identificador.

        Args:
            offering_id: identificador del grupo.

        Returns:
            El grupo, o `None` si no existe.
        """

    @abstractmethod
    def find_by_course_and_period(
        self, course_id: UUID, enrollment_period_id: UUID
    ) -> list[CourseOffering]:
        """Recupera los grupos de una materia dentro de un período.

        Es la consulta que resuelve `GET /courses/{id}/offerings`.

        Args:
            course_id: identificador de la materia.
            enrollment_period_id: identificador del período de matrícula.

        Returns:
            Los grupos ordenados por número de grupo, o una lista vacía si la materia no se
            ofrece en ese período.
        """

    @abstractmethod
    def find_course_ids_offered_in(
        self, course_ids: Sequence[UUID], enrollment_period_id: UUID
    ) -> set[UUID]:
        """Indica cuáles de esas materias tienen al menos un grupo abierto en el período.

        Es `find_by_course_and_period` en lote y reducido a un sí o un no. Existe para el
        semáforo del plan de estudios, que necesita la respuesta para las decenas de materias
        de un plan a la vez: preguntarlo materia por materia sería un N+1 sobre una pantalla
        que se abre entera de golpe.

        Devuelve solo identificadores y no los grupos porque quien pregunta no va a mostrarlos.
        Traer los grupos con su docente y su horario para acabar comprobando si la lista está
        vacía sería mover a la aplicación datos que nadie lee.

        Args:
            course_ids: materias por las que se pregunta.
            enrollment_period_id: período sobre el que mirar.

        Returns:
            Las materias con oferta. Vacío si ninguna se ofrece.
        """

    @abstractmethod
    def find_by_ids(self, offering_ids: Sequence[UUID]) -> list[CourseOffering]:
        """Recupera varios grupos de una vez, con su docente y su horario resueltos.

        Existe para la detección de choque de horario: el caso de uso tiene los identificadores
        de los grupos que el estudiante ya cursa y necesita sus franjas. Pedirlos uno a uno
        sería un N+1 dentro de la transacción crítica de la inscripción, que es el peor sitio
        posible para tenerlo.

        Args:
            offering_ids: identificadores de los grupos.

        Returns:
            Los grupos encontrados, ordenados por número de grupo. Los identificadores que no
            existan se omiten en silencio: quien llama pregunta por un conjunto, no comprueba
            existencia.
        """

    @abstractmethod
    def try_reserve_slot(self, offering_id: UUID) -> bool:
        """Ocupa un cupo del grupo de forma atómica, o informa de que ya no quedan.

        Es el punto exacto donde se decide quién gana el último cupo, y la razón de que el
        sobrecupo sea imposible.

        La implementación debe ser **una sola sentencia** que compruebe la capacidad y
        descuente el cupo a la vez, sin leer antes. Es lo que impide que dos transacciones
        pasen la comprobación con el mismo estado: PostgreSQL serializa el acceso a la fila, y
        la segunda evalúa la condición contra el valor que la primera ya escribió.

        POR QUÉ NO SE CONDICIONA POR `version`. El diseño original de `DATA_MODEL.md` proponía
        `WHERE version = :esperada` con reintentos. Se implementó y se midió, y no escala: con
        N transacciones sobre la misma fila solo una gana por ronda, así que harían falta hasta
        N reintentos. Con 40 concurrentes y 100 cupos libres solo entraban 10 —a 30 personas se
        les rechazaba un cupo que existía—. Condicionar por `enrolled_count < total_capacity`
        elimina el problema de raíz: cada transacción reevalúa la condición real contra el
        estado actual, nadie es rechazado sin motivo y no hace falta reintentar nunca.

        `version` se sigue incrementando en la misma sentencia. Conserva su valor como marca de
        modificación y para el bloqueo optimista de otras operaciones sobre el grupo —ajustar
        la capacidad desde administración, en la Fase 4—, donde los conflictos sí son raros y
        el mecanismo por versión es el adecuado.

        Args:
            offering_id: identificador del grupo.

        Returns:
            `True` si quedó un cupo ocupado; `False` si el grupo estaba lleno o no existe.
        """

    @abstractmethod
    def try_release_slot(self, offering_id: UUID) -> bool:
        """Libera un cupo del grupo de forma atómica, al cancelarse una inscripción.

        Igual que su contraria, en una sola sentencia y condicionada: solo descuenta si el
        contador es mayor que cero. Sin esa guarda, una cancelación procesada dos veces dejaría
        `enrolled_count` por debajo de la ocupación real, y ese hueco fantasma lo podrían tomar
        dos personas.

        Args:
            offering_id: identificador del grupo.

        Returns:
            `True` si se liberó un cupo; `False` si el contador ya estaba en cero o el grupo no
            existe.
        """

    @abstractmethod
    def count_enrolled(self, offering_id: UUID) -> int | None:
        """Lee el número de cupos ocupados directamente de la base de datos.

        Existe separado de `find_by_id` por una razón concreta: la disponibilidad de cupos
        **nunca se cachea** (`CLAUDE.md`). El resto del grupo —materia, docente, horario,
        capacidad— cambia una vez por semestre y se cachea sin problema, pero
        `enrolled_count` cambia miles de veces durante la ventana de matrícula. Este método
        permite servir la parte estática desde la caché y refrescar solo el contador con una
        lectura mínima a PostgreSQL.

        Args:
            offering_id: identificador del grupo.

        Returns:
            Los cupos ocupados, o `None` si el grupo ya no existe.
        """

    @abstractmethod
    def save(self, offering: CourseOffering) -> None:
        """Persiste un grupo nuevo junto con sus franjas de horario.

        Las franjas se guardan en la misma llamada, no en un puerto aparte: en el dominio no
        tienen identidad propia —son value objects dentro del grupo— y un grupo publicado sin
        su horario es un estado que nadie debería poder observar.

        No confirma la transacción; de eso se encarga la `UnitOfWork` del caso de uso.

        Args:
            offering: el grupo a persistir, con su horario ya completo.
        """

    @abstractmethod
    def update_capacity(
        self, offering_id: UUID, *, new_capacity: int, expected_version: int
    ) -> bool:
        """Cambia el cupo total del grupo si nadie lo ha modificado entretanto.

        Aquí sí se condiciona por `version`, al contrario que en `try_reserve_slot`. La razón
        es la contención esperada: dos administradores ajustando el mismo grupo a la vez es
        excepcional, así que el bloqueo optimista casi nunca falla y, cuando falla, rechazar es
        justo lo que se quiere —la alternativa sería que la segunda escritura pisara en
        silencio la decisión de la primera—. En el descuento de cupo la contención es la norma
        y condicionar por versión rechazaba inscripciones legítimas; por eso allí se condiciona
        por `enrolled_count < total_capacity`.

        La sentencia lleva además `WHERE enrolled_count <= :new_capacity`, y no es redundante
        con la comprobación previa del caso de uso: entre leer el grupo y escribirlo pueden
        entrar inscripciones nuevas, y sin esa condición el `UPDATE` chocaría contra el
        `CHECK (enrolled_count <= total_capacity)` y abortaría la transacción entera.

        Args:
            offering_id: identificador del grupo.
            new_capacity: cupo total que se quiere dejar.
            expected_version: versión que tenía el grupo cuando se leyó.

        Returns:
            `True` si el cupo quedó ajustado; `False` si el grupo cambió entretanto, ya no
            existe, o el cupo pedido es menor que la ocupación actual.
        """
