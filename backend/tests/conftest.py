"""Fixtures compartidas por toda la suite de pruebas del backend."""

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

# La configuración es obligatoria y se resuelve al importar la aplicación, así que se fijan
# valores por defecto antes de ese import. `setdefault` no pisa el entorno real: si el CI o
# docker-compose ya definieron estas variables, mandan las suyas. Los valores de aquí no
# apuntan a ningún servicio real; en Fase 0 nada los usa todavía.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://matricula:matricula@localhost:5432/matricula_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "jwt-secret-solo-para-pruebas")

from app.interfaces.api.main import app  # noqa: E402


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Cliente HTTP de pruebas contra la aplicación FastAPI real.

    Se usa como context manager para que se ejecuten los eventos de arranque y apagado de la
    aplicación, igual que en producción.

    Yields:
        TestClient: cliente listo para hacer peticiones a `app`.
    """
    with TestClient(app) as test_client:
        yield test_client
