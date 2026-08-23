"""Adaptador de `UnitOfWork` sobre una sesión de SQLAlchemy."""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.orm import Session

from app.application.ports.unit_of_work import UnitOfWork


class SQLAlchemyUnitOfWork(UnitOfWork):
    """Frontera transaccional sobre la sesión de la petición.

    Recibe la MISMA sesión que usan los repositorios, y eso no es un detalle: si abriera una
    propia, las escrituras de los repositorios quedarían en una transacción distinta de la que
    este objeto confirma, y el `commit` no guardaría nada de lo que el caso de uso creyó
    escribir. El cableado de `di.py` garantiza que la sesión sea una sola por petición.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def __enter__(self) -> SQLAlchemyUnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Revierte lo que no se haya confirmado.

        Se llama `rollback()` siempre, también en la salida limpia. No deshace un `commit`
        anterior —una transacción ya confirmada es inmutable— pero sí descarta cualquier cosa
        escrita después de él, y cierra la transacción implícita que SQLAlchemy abre al leer.
        Lo importante es lo que garantiza: salir del bloque sin haber confirmado nunca deja
        escrituras a medias, ni siquiera si nadie lanzó una excepción.
        """
        self._session.rollback()

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

    def flush(self) -> None:
        self._session.flush()
