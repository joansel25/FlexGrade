"""baseline: inicializa el sistema de migraciones

Migracion vacia a proposito. No crea ninguna tabla: su unico objetivo es
establecer el punto de partida del historial de Alembic (crear la tabla
``alembic_version`` y fijar la cabeza de la que colgaran las migraciones
reales, que empiezan en la Fase 1 con los modelos de autenticacion).

Tener una baseline explicita evita que la primera migracion con contenido
tenga ``down_revision = None`` y permite que un entorno recien levantado y uno
ya existente compartan exactamente el mismo historial.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-22
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Sin cambios de esquema: la baseline solo marca el inicio del historial."""
    pass


def downgrade() -> None:
    """Sin cambios de esquema que revertir."""
    pass
