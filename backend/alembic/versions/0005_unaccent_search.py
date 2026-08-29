"""busqueda: extension unaccent para que el catalogo encuentre sin tildes

Un estudiante que busca "calculo" tiene que encontrar "Cálculo I". Sin esta extension no lo
encuentra: `ILIKE` normaliza mayusculas pero no diacriticos, asi que 'a' y 'á' son caracteres
distintos y el patron '%calculo%' no casa con 'Cálculo'.

Es un defecto de usabilidad real y no un detalle: en un sistema academico en espanol, la
mayoria de los nombres de materia llevan tilde y casi nadie las escribe al buscar. La busqueda
del catalogo devolveria cero resultados justo en las materias mas buscadas.

`unaccent` viene en el paquete `postgresql-contrib`, que la imagen oficial `postgres:16` ya
incluye, y esta disponible en Azure Database for PostgreSQL.

NOTA SOBRE INDICES: `unaccent()` se declara STABLE y no IMMUTABLE, asi que no puede usarse
directamente en un indice de expresion. A la escala del catalogo —15 materias hoy, algunos
cientos en produccion— un escaneo secuencial es irrelevante. Si algun dia el catalogo creciera
lo suficiente, la solucion es envolverla en una funcion propia marcada IMMUTABLE y crear un
indice GIN con `pg_trgm`. No se hace ahora porque seria optimizar sin medir.

Revision ID: 0005_unaccent_search
Revises: 0004_catalog_tables
Create Date: 2026-08-23
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005_unaccent_search"
down_revision: str | None = "0004_catalog_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Instala la extension `unaccent`."""
    # `IF NOT EXISTS` la hace idempotente: un entorno donde ya este instalada no falla.
    op.execute('CREATE EXTENSION IF NOT EXISTS "unaccent"')


def downgrade() -> None:
    """Desinstala la extension.

    Si alguna consulta la sigue usando, PostgreSQL rechaza el DROP. Es lo correcto: preferible
    un error explicito a dejar la aplicacion con una funcion que ya no existe.
    """
    op.execute('DROP EXTENSION IF EXISTS "unaccent"')
