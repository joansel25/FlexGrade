"""Puerto de la frontera transaccional.

La inscripción escribe en DOS tablas: descuenta el cupo en `course_offerings` y crea la fila en
`enrollments`. Si una de las dos se aplicara sin la otra el sistema quedaría en un estado
imposible —un cupo descontado que nadie ocupa, o una inscripción que no descontó nada— y ningún
`CHECK` lo detectaría, porque cada fila por separado sería válida.

`UnitOfWork` marca los límites de esa atomicidad. Es un puerto y no una llamada directa a
`Session.commit()` porque el caso de uso vive en la capa de aplicación y no puede conocer
SQLAlchemy: eso es la inversión de dependencias (`ARCHITECTURE.md` sección 5, principio D).

No se añadió antes a propósito. Las Fases 1 y 2 solo leían, y un puerto sin quien lo use es
código muerto con aspecto de arquitectura. Llega ahora, que es cuando hay una operación que de
verdad lo necesita.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType


class UnitOfWork(ABC):
    """Contrato de una transacción explícita.

    Se usa como gestor de contexto:

        with uow:
            offering.reserve_slot()
            offering_repository.update_with_version_check(offering, esperada)
            enrollment_repository.save(enrollment)
            uow.commit()

    Si algo falla dentro del `with` —una excepción de dominio, un fallo de red, un conflicto de
    versión— la salida revierte todo. Y si el bloque termina sin llamar a `commit()`, también
    revierte: olvidarse de confirmar nunca puede dejar una escritura a medias.
    """

    @abstractmethod
    def __enter__(self) -> UnitOfWork:
        """Abre la transacción."""

    @abstractmethod
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Cierra la transacción, revirtiendo si no se confirmó."""

    @abstractmethod
    def commit(self) -> None:
        """Confirma todo lo escrito en esta transacción."""

    @abstractmethod
    def rollback(self) -> None:
        """Descarta todo lo escrito en esta transacción."""

    @abstractmethod
    def flush(self) -> None:
        """Envía a la base de datos lo pendiente, sin confirmar.

        Hace falta para el bloqueo optimista: el `UPDATE` con `WHERE version = :esperada`
        tiene que ejecutarse —y devolver cuántas filas afectó— ANTES de decidir si la
        transacción se confirma o se reintenta. Sin `flush`, SQLAlchemy podría retrasar la
        escritura hasta el `commit` y para entonces ya sería tarde para detectar el conflicto.
        """
