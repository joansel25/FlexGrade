"""Puerto de persistencia de los espacios físicos.

Segregado en lector y escritor, como `EnrollmentRepository` (`ARCHITECTURE.md` sección 5,
principio I). Quien asigna un aula a un grupo solo necesita resolverla; hacerle depender de un
contrato que además crea espacios le daría acceso a una operación que no le corresponde y le
obligaría a implementarla al construir un doble de prueba.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from app.domain.entities.space import Space


class SpaceReader(ABC):
    """Contrato de consulta del inventario de espacios."""

    @abstractmethod
    def find_by_id(self, space_id: UUID) -> Space | None:
        """Recupera un espacio por su identificador.

        Args:
            space_id: identificador del espacio.

        Returns:
            El espacio, o `None` si no existe.
        """

    @abstractmethod
    def find_by_code(self, code: str) -> Space | None:
        """Recupera un espacio por su código institucional.

        El código es la CLAVE NATURAL del espacio, y por eso esta consulta existe: `A-201` es lo
        que aparece en un horario impreso y lo que alguien escribe al asignar un aula, así que la
        API la acepta en vez de exigir un UUID que nadie tiene a mano. Es el mismo criterio que
        ya sigue `CourseRepository.find_by_code`.

        La comparación NO distingue mayúsculas ni espacios sobrantes: quien escribe `a-201 `
        se refiere al mismo salón que quien escribe `A-201`, y obligarle a acertar el formato
        exacto convertiría un dato correcto en un 404.

        Args:
            code: código del espacio.

        Returns:
            El espacio, o `None` si no existe.
        """

    @abstractmethod
    def find_by_ids(self, space_ids: Sequence[UUID]) -> dict[UUID, Space]:
        """Recupera varios espacios de una vez, indexados por identificador.

        Existe para resolver el aula de las franjas de un horario en una sola consulta. Pedirlas
        de una en una sería un N+1 sobre pantallas que muestran el horario completo.

        Args:
            space_ids: identificadores de los espacios.

        Returns:
            Los espacios encontrados. Los identificadores inexistentes se omiten.
        """

    @abstractmethod
    def search(self, *, space_type: str | None = None, campus: str | None = None) -> list[Space]:
        """Lista el inventario de espacios, con filtros opcionales.

        Sin paginar, al contrario que el catálogo de materias: una institución tiene decenas o
        pocos cientos de espacios, no miles, y quien va a asignar un aula necesita verlos todos
        para elegir.

        Args:
            space_type: si se indica, solo los de ese tipo.
            campus: si se indica, solo los de esa sede.

        Returns:
            Los espacios que cumplen los filtros, ordenados por código.
        """


class SpaceWriter(ABC):
    """Contrato de escritura del inventario de espacios."""

    @abstractmethod
    def save(self, space: Space) -> None:
        """Persiste un espacio nuevo o los cambios de uno existente.

        No confirma la transacción: eso le corresponde a la `UnitOfWork` del caso de uso.

        Args:
            space: el espacio a persistir.
        """


class SpaceRepository(SpaceReader, SpaceWriter):
    """Contrato completo, para quien necesita leer y escribir."""
