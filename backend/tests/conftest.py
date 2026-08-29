"""Fixtures compartidas por toda la suite de pruebas del backend.

AISLAMIENTO DE LA BASE DE DATOS. Los tests de integración vacían tablas enteras al terminar
cada caso. Si corrieran contra la base de desarrollo, `make test-int` borraría los datos de
`make seed` y habría que volver a sembrarlos cada vez —y, peor, cualquier dato de prueba que
alguien estuviera usando a mano—.

Por eso, si el entorno no dice otra cosa, la suite redirige `DATABASE_URL` a una base
**distinta**, con el sufijo `_test`. El CI sí define su propia `DATABASE_URL` (que ya apunta a
`matricula_test`) y esa manda: aquí solo se cubre el caso de correr los tests en local contra
`docker-compose`. Lo mismo con Redis: se usa una base lógica aparte, la 1 en vez de la 0.

Este módulo se limita a **reescribir cadenas de configuración**. No abre ninguna conexión, y
esa distinción es importante: los tests unitarios tienen que poder ejecutarse sin PostgreSQL ni
Redis levantados, que es exactamente lo que hace el CI en su paso de unitarios. Crear la base
de datos y aplicarle las migraciones ocurre en `tests/integration/conftest.py`, donde solo
afecta a los tests que de verdad la necesitan.
"""

import os
from collections.abc import Iterator
from urllib.parse import urlparse, urlunparse

import pytest
from fastapi.testclient import TestClient

SUFIJO_DE_PRUEBAS = "_test"
_INDICE_REDIS_DE_PRUEBAS = "1"


def _url_de_pruebas(url: str) -> str:
    """Devuelve la misma URL apuntando a la base de datos de pruebas.

    Si la base ya termina en `_test` la deja intacta: es lo que ocurre en el CI, donde el
    servicio de PostgreSQL del runner ya se llama así.
    """
    partes = urlparse(url)
    nombre = partes.path.lstrip("/")

    if nombre.endswith(SUFIJO_DE_PRUEBAS):
        return url

    return urlunparse(partes._replace(path=f"/{nombre}{SUFIJO_DE_PRUEBAS}"))


def _redis_de_pruebas(url: str) -> str:
    """Devuelve la misma URL de Redis apuntando a una base lógica reservada a los tests."""
    partes = urlparse(url)
    return urlunparse(partes._replace(path=f"/{_INDICE_REDIS_DE_PRUEBAS}"))


# La configuración es obligatoria y se resuelve al importar la aplicación, así que todo esto
# tiene que ocurrir ANTES de ese import. Son valores por defecto para poder importar la app;
# ninguno se usa para conectarse hasta que un test de integración lo pide.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://matricula:devpassword@postgres:5432/matricula"
)
os.environ.setdefault("REDIS_URL", "redis://redis:6379/0")
os.environ.setdefault("JWT_SECRET", "jwt-secret-solo-para-pruebas")
# El origen del frontend en desarrollo. Se fija aquí y no solo en `docker-compose.yml`
# para que la suite compruebe CORS aunque corra en un contenedor levantado antes de que
# la variable existiera, o en el runner del CI, que no usa `docker-compose`.
os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://localhost:5173")

# EL LIMITADOR VA APAGADO EN LA SUITE, y no por comodidad. La mayoría de los tests de
# integración hacen decenas de peticiones seguidas con la misma cuenta y desde la misma
# dirección: con el límite puesto, el de inscripción (30/min) tumbaría el test de concurrencia
# y el de administración (60/min) los de reportes, con un 429 que no tiene nada que ver con lo
# que ese test comprueba. Peor aún, fallarían de forma INTERMITENTE, según cuántos tests
# hubieran corrido antes dentro del mismo minuto.
#
# Los tests que sí prueban el limitador lo encienden ellos, con `monkeypatch` sobre la
# configuración: es la única forma de que la protección se pruebe de verdad sin contaminar al
# resto de la suite.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

os.environ["DATABASE_URL"] = _url_de_pruebas(os.environ["DATABASE_URL"])
os.environ["REDIS_URL"] = _redis_de_pruebas(os.environ["REDIS_URL"])

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
