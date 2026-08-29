"""Entorno de ejecucion de Alembic.

La URL de la base de datos NO se lee de ``alembic.ini`` (ahi ``sqlalchemy.url``
queda vacio a proposito, para no comitear credenciales). Se obtiene del modulo
de configuracion de la aplicacion, que la toma de la variable de entorno
``DATABASE_URL``. Asi las migraciones y la aplicacion usan siempre exactamente
la misma configuracion en cada ambiente (12-factor).
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.infrastructure.config.settings import get_settings

# El import del paquete `models` completo (y no solo de `Base`) es deliberado: es lo que
# registra cada modelo en `Base.metadata`. Un modelo no importado quedaria fuera del catalogo y
# `--autogenerate` lo interpretaria como una tabla sobrante que hay que borrar.
from app.infrastructure.persistence.sqlalchemy import models

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# La URL se usa directamente y no se escribe en `config`: ConfigParser interpreta
# el caracter "%" como interpolacion y romperia una contrasena que lo contenga.
#
# Se lee primero de la variable de entorno y solo despues de la configuracion de la
# aplicacion. La diferencia importa en el paso de migraciones del pipeline: ahi se ejecuta
# Alembic contra el Flexible Server pero NO se levanta la aplicacion, asi que `REDIS_URL` y
# `JWT_SECRET` —obligatorios para `Settings`— no tienen por que estar definidos. Exigirlos
# haria fallar el despliegue en el paso previo a tocar el esquema, por dos valores que la
# migracion no usa.
DATABASE_URL = os.environ.get("DATABASE_URL") or get_settings().database_url

# Catalogo contra el que Alembic compara el esquema real de la base de datos para generar
# migraciones con `--autogenerate`. Autogenerate es una ayuda, no una autoridad: no detecta la
# extension `pgcrypto`, ni los renombres (los ve como DROP + ADD, con perdida de datos), y
# traduce mal algunos `CHECK` y `server_default`. Cada archivo generado se revisa a mano.
target_metadata = models.Base.metadata


def run_migrations_offline() -> None:
    """Genera el SQL de las migraciones sin conectarse a la base de datos.

    Es el modo que usa el despliegue a produccion para el dry-run con ``--sql``
    descrito en CI_CD.md seccion 4.4.
    """
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Aplica las migraciones contra la base de datos configurada."""
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
