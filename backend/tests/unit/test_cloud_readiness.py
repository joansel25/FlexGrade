"""Pruebas de la configuración que hace desplegable el backend en Azure.

Todo lo que se comprueba aquí falla, si falla, en el peor momento posible: durante un
despliegue o en pleno pico de matrícula, cuando ya no hay nadie mirando el código. Son
comprobaciones baratas de un puñado de decisiones que la nube da por supuestas.
"""

from __future__ import annotations

import json
import logging

import pytest

from app.infrastructure.config.settings import Settings
from app.infrastructure.logging.setup import FormateadorJSON, configurar_logging

_MINIMOS = {
    "database_url": "postgresql+psycopg://u:p@postgres:5432/matricula",
    "redis_url": "redis://redis:6379/0",
    "jwt_secret": "secreto-de-prueba",
}


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_los_origenes_cors_se_leen_de_una_cadena_separada_por_comas() -> None:
    """Una variable de entorno no puede ser una lista; Azure App Service solo pasa cadenas."""
    settings = Settings(
        **_MINIMOS,
        cors_allowed_origins="https://d123.azurefd.net, http://localhost:5173",
    )

    assert settings.cors_allowed_origins == [
        "https://d123.azurefd.net",
        "http://localhost:5173",
    ]


@pytest.mark.unit
def test_una_lista_de_origenes_vacia_no_autoriza_a_nadie() -> None:
    """Ese es el valor por defecto: el permiso se concede explícitamente, no se hereda.

    Se pasa la cadena vacía en vez de omitir el campo porque la suite fija la variable de
    entorno para poder probar CORS, y Pydantic Settings la leería igualmente.
    """
    assert Settings(**_MINIMOS, cors_allowed_origins="").cors_allowed_origins == []


@pytest.mark.unit
def test_el_tamano_del_pool_es_configurable() -> None:
    """El límite lo pone `max_connections` del servidor, repartido entre todas las instancias."""
    settings = Settings(**_MINIMOS, db_pool_size=5, db_max_overflow=5)

    assert (settings.db_pool_size, settings.db_max_overflow) == (5, 5)


@pytest.mark.unit
def test_la_documentacion_interactiva_se_puede_apagar() -> None:
    """`/docs` expone el mapa completo de la API, incluido lo de administración."""
    assert Settings(**_MINIMOS, docs_enabled=False).docs_enabled is False


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_cada_registro_es_una_linea_json_con_sus_campos() -> None:
    """Azure Monitor trocea por línea: un JSON multilínea llegaría partido y sería inservible."""
    registro = logging.LogRecord(
        name="app.request",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="peticion atendida",
        args=None,
        exc_info=None,
    )
    registro.status_code = 200
    registro.path = "/api/v1/enrollments"

    salida = FormateadorJSON().format(registro)

    assert "\n" not in salida
    datos = json.loads(salida)
    # Los campos que se pasaron por `extra=` viajan sueltos, consultables en Insights.
    assert datos["status_code"] == 200
    assert datos["path"] == "/api/v1/enrollments"
    assert datos["level"] == "INFO"
    assert datos["message"] == "peticion atendida"


@pytest.mark.unit
def test_el_json_no_arrastra_los_atributos_internos_de_logging() -> None:
    """Sin el filtro, cada línea llevaría treinta claves de ruido y costaría almacenarlas."""
    registro = logging.LogRecord(
        name="app",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hola",
        args=None,
        exc_info=None,
    )

    datos = json.loads(FormateadorJSON().format(registro))

    for interno in ("msg", "args", "levelno", "pathname", "lineno"):
        assert interno not in datos


@pytest.mark.unit
def test_la_traza_de_una_excepcion_cabe_en_un_solo_campo() -> None:
    try:
        raise ValueError("fallo de prueba")
    except ValueError:
        registro = logging.LogRecord(
            name="app",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="fallo",
            args=None,
            exc_info=True,
        )
        import sys

        registro.exc_info = sys.exc_info()
        salida = FormateadorJSON().format(registro)

    assert "\n" not in salida
    assert "ValueError" in json.loads(salida)["exception"]


@pytest.mark.unit
def test_configurar_logging_reemplaza_los_manejadores_en_vez_de_sumarse() -> None:
    """Sumarse a los de uvicorn duplicaría cada evento: uno en JSON y otro en texto plano."""
    raiz = logging.getLogger()
    originales = raiz.handlers[:]
    nivel_original = raiz.level

    try:
        configurar_logging(level="INFO", json_format=True)
        configurar_logging(level="WARNING", json_format=True)

        assert len(raiz.handlers) == 1
        assert raiz.level == logging.WARNING
    finally:
        raiz.handlers = originales
        raiz.setLevel(nivel_original)
        logging.getLogger("uvicorn.access").disabled = False
