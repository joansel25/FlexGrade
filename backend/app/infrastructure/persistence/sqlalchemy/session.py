"""Construcción del engine y de las sesiones de SQLAlchemy.

Es el único módulo que abre la conexión a PostgreSQL. La URL sale de
`Settings.database_url`, que a su vez la lee de la variable de entorno
`DATABASE_URL` (12-factor): el código no contiene ninguna credencial.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.config.settings import get_settings


@lru_cache
def get_engine() -> Engine:
    """Devuelve el engine de SQLAlchemy, creado una sola vez por proceso.

    El pool se dimensiona pensando en la ventana de matrícula: `pool_size`
    cubre la carga sostenida y `max_overflow` absorbe los picos sin que las
    peticiones esperen a que se libere una conexión. `pool_pre_ping` descarta
    conexiones que RDS haya cerrado por inactividad, que de otro modo fallarían
    en la primera consulta tras un periodo de calma.

    Los dos tamaños llegan por variable de entorno, y no son un detalle de
    ajuste fino: el límite real lo pone RDS, cuyo `max_connections` se reparte
    entre TODAS las instancias que levante el autoescalado. Con los valores por
    defecto (10 + 20), cuatro instancias agotan una `db.t3.micro`; la quinta
    empieza a recibir «too many connections» justo en el pico. Poder bajarlos
    desde Elastic Beanstalk evita tener que reconstruir y redesplegar la imagen
    en mitad de una matrícula.

    Returns:
        El engine compartido por toda la aplicación.
    """
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        # Recicla las conexiones cada media hora. RDS y el balanceador cortan las
        # conexiones inactivas por su cuenta; renovarlas antes evita que la
        # aplicación descubra el corte a mitad de una transacción.
        pool_recycle=1800,
        future=True,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    """Devuelve la factoría de sesiones, creada una sola vez por proceso.

    `expire_on_commit=False` evita que SQLAlchemy invalide los objetos tras el
    commit: los repositorios ya han traducido los modelos ORM a entidades del
    dominio, y recargarlos supondría consultas extra sin ninguna utilidad.

    Returns:
        La factoría de sesiones ligada al engine de la aplicación.
    """
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


def get_session() -> Iterator[Session]:
    """Entrega una sesión por petición y garantiza su cierre.

    Se usa como dependencia de FastAPI. Si el handler lanza una excepción, la
    transacción se revierte antes de cerrar; así un fallo a mitad de una
    operación nunca deja escrituras parciales en la base de datos.

    Yields:
        La sesión activa durante la petición.
    """
    session = get_session_factory()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
