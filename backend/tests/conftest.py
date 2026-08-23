"""Fixtures compartidas por toda la suite de pruebas del backend.

AISLAMIENTO DE LA BASE DE DATOS. Los tests de integración vacían tablas enteras al terminar
cada caso. Si corrieran contra la base de desarrollo, `make test-int` borraría los datos de
`make seed` y habría que volver a sembrarlos cada vez —y, peor, cualquier dato de prueba que
alguien estuviera usando a mano—.

Por eso, si el entorno no dice otra cosa, la suite redirige `DATABASE_URL` a una base
**distinta**, con el sufijo `_test`, y la crea si no existe. El CI sí define su propia
`DATABASE_URL` (que ya apunta a `matricula_test`) y esa manda: aquí solo se cubre el caso de
correr los tests en local contra `docker-compose`.

Lo mismo con Redis: se usa una base lógica aparte (la 1 en vez de la 0), para que vaciar las
claves del catálogo entre tests no toque la caché con la que estés trabajando.
"""

import os
from collections.abc import Iterator
from urllib.parse import urlparse, urlunparse

import psycopg
import pytest
from fastapi.testclient import TestClient

_SUFIJO_DE_PRUEBAS = "_test"
_INDICE_REDIS_DE_PRUEBAS = "1"


def _url_de_pruebas(url: str) -> str:
    """Devuelve la misma URL apuntando a la base de datos de pruebas.

    Si la base ya termina en `_test` la deja intacta: es lo que ocurre en el CI, donde el
    servicio de PostgreSQL del runner ya se llama así.
    """
    partes = urlparse(url)
    nombre = partes.path.lstrip("/")

    if nombre.endswith(_SUFIJO_DE_PRUEBAS):
        return url

    return urlunparse(partes._replace(path=f"/{nombre}{_SUFIJO_DE_PRUEBAS}"))


def _crear_base_si_falta(url: str) -> None:
    """Crea la base de datos de pruebas si todavía no existe.

    `CREATE DATABASE` no admite ejecutarse dentro de una transacción, de ahí el `autocommit`.
    Se conecta a `postgres`, la base de mantenimiento que siempre está presente.
    """
    partes = urlparse(url)
    objetivo = partes.path.lstrip("/")
    # `psycopg.connect` no entiende el prefijo de dialecto de SQLAlchemy.
    mantenimiento = urlunparse(partes._replace(scheme="postgresql", path="/postgres"))

    with psycopg.connect(mantenimiento, autocommit=True) as conexion:
        existe = conexion.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (objetivo,)
        ).fetchone()

        if existe is None:
            conexion.execute(f'CREATE DATABASE "{objetivo}"')


def _redis_de_pruebas(url: str) -> str:
    """Devuelve la misma URL de Redis apuntando a una base lógica reservada a los tests."""
    partes = urlparse(url)
    return urlunparse(partes._replace(path=f"/{_INDICE_REDIS_DE_PRUEBAS}"))


# La configuración es obligatoria y se resuelve al importar la aplicación, así que todo esto
# tiene que ocurrir ANTES de ese import.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://matricula:devpassword@postgres:5432/matricula"
)
os.environ.setdefault("REDIS_URL", "redis://redis:6379/0")
os.environ.setdefault("JWT_SECRET", "jwt-secret-solo-para-pruebas")

os.environ["DATABASE_URL"] = _url_de_pruebas(os.environ["DATABASE_URL"])
os.environ["REDIS_URL"] = _redis_de_pruebas(os.environ["REDIS_URL"])

from app.interfaces.api.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def base_de_datos_de_pruebas() -> None:
    """Prepara la base de datos de pruebas antes de que corra ningún test.

    La crea si falta y aplica todas las migraciones. Usar Alembic —y no un `create_all`—
    significa que los tests corren contra exactamente el mismo esquema que DEV, STAGING y
    PROD, incluidos los triggers, los índices parciales y los `CHECK` que `create_all` no
    reproduce.
    """
    from alembic import command
    from alembic.config import Config

    url = os.environ["DATABASE_URL"]
    _crear_base_si_falta(url)

    configuracion = Config("alembic.ini")
    command.upgrade(configuracion, "head")


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
