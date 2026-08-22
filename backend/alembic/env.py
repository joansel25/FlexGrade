"""Entorno de ejecucion de Alembic.

La URL de la base de datos NO se lee de ``alembic.ini`` (ahi ``sqlalchemy.url``
queda vacio a proposito, para no comitear credenciales). Se obtiene del modulo
de configuracion de la aplicacion, que la toma de la variable de entorno
``DATABASE_URL``. Asi las migraciones y la aplicacion usan siempre exactamente
la misma configuracion en cada ambiente (12-factor).
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.infrastructure.config.settings import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# La URL se usa directamente y no se escribe en `config`: ConfigParser interpreta
# el caracter "%" como interpolacion y romperia una contrasena que lo contenga.
DATABASE_URL = get_settings().database_url

# Fase 0: todavia no existen modelos ORM, por lo que no hay metadata que comparar.
# Cuando aparezca la primera entidad persistida (Fase 1), aqui se importa la
# `Base` declarativa y se asigna `target_metadata = Base.metadata` para habilitar
# `alembic revision --autogenerate`.
target_metadata = None


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
