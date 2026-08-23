"""Clase declarativa base de la que heredan todos los modelos ORM.

Concentra dos decisiones que afectan a todo el esquema:

1. **Convención de nombres de restricciones.** PostgreSQL genera nombres automáticos
   (`users_email_key`, `students_user_id_fkey`) que dependen del motor y son difíciles de
   referenciar desde una migración posterior. Fijar una `naming_convention` en el `MetaData`
   hace que cada índice, restricción única, `CHECK`, clave foránea y clave primaria reciba un
   nombre determinista y estable, imprescindible para escribir `op.drop_constraint(...)` sin
   adivinar.
2. **Aislamiento del dominio.** Esta `Base` vive en `infrastructure/` y ninguna clase que la
   herede contiene lógica de negocio: los modelos son solo el mapeo de las tablas descritas en
   `docs/DATA_MODEL.md`. Los repositorios traducen entre modelo ORM y entidad del dominio.

Nota sobre los `CHECK`: la plantilla `ck` interpola `constraint_name`, por lo que al declarar
una restricción hay que pasar el nombre **corto** (`name="role"`), no el completo. La convención
lo expande a `ck_users_role`. Pasar el nombre ya completo produciría `ck_users_ck_users_role`.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Raíz de la jerarquía declarativa de SQLAlchemy 2.x.

    `Base.metadata` es el catálogo que Alembic compara contra la base de datos real para
    generar migraciones con `--autogenerate`; por eso `alembic/env.py` importa el paquete
    `models` completo, no solo esta clase: un modelo que no se importe no aparece en el
    `MetaData` y Alembic lo interpretaría como una tabla sobrante que hay que borrar.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
