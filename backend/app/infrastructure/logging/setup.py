"""Configuración del logging de la aplicación.

**Por qué JSON y por qué a stdout.** En Elastic Beanstalk nadie entra a la máquina a leer un
archivo: el contenedor escribe a stdout, el agente lo recoge y lo entrega a CloudWatch Logs. Si
las líneas son texto libre, CloudWatch guarda cadenas y buscar «todos los 500 del endpoint de
inscripción» obliga a inventar expresiones regulares sobre el mensaje. Si son JSON, CloudWatch
Logs Insights consulta por campo:

    fields @timestamp, path, status_code, duration_ms
    | filter status_code >= 500
    | sort duration_ms desc

Escribir a un archivo sería peor todavía: las instancias del autoescalado son efímeras y se
destruyen al bajar el pico, y con ellas cualquier registro que no haya salido del disco.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Atributos que `logging` pone en todos los registros. Se listan para poder distinguir los
# campos que añade quien llama (`extra={...}`) de los que trae la biblioteca, y volcar solo los
# primeros al JSON: sin este filtro, cada línea arrastraría treinta claves de ruido.
_ATRIBUTOS_ESTANDAR = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys()) | {
    "message",
    "asctime",
    "taskName",
}


class FormateadorJSON(logging.Formatter):
    """Formatea cada registro como una línea JSON.

    Una línea por evento, sin saltos de línea dentro: CloudWatch trocea por línea, así que un
    JSON indentado se rompería en fragmentos que ya no son JSON válido.
    """

    def format(self, record: logging.LogRecord) -> str:
        datos: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Todo lo que se pasó por `extra=` viaja como campo propio, consultable en Insights.
        for clave, valor in record.__dict__.items():
            if clave not in _ATRIBUTOS_ESTANDAR:
                datos[clave] = valor

        if record.exc_info:
            # La traza completa, en un solo campo, para que el JSON siga siendo una línea.
            datos["exception"] = self.formatException(record.exc_info)

        return json.dumps(datos, ensure_ascii=False, default=str)


def configurar_logging(*, level: str, json_format: bool) -> None:
    """Deja el logging listo para el entorno en el que corre la aplicación.

    Se llama una sola vez, al importar la aplicación. Reemplaza los manejadores existentes en
    vez de añadir uno: uvicorn instala los suyos al arrancar y, sin esa sustitución, cada
    evento se registraría dos veces —una en JSON y otra en texto plano—.

    Args:
        level: nivel mínimo (`DEBUG`, `INFO`, `WARNING`, `ERROR`).
        json_format: `True` para JSON de una línea (nube), `False` para texto legible (local).
    """
    manejador = logging.StreamHandler(sys.stdout)

    if json_format:
        manejador.setFormatter(FormateadorJSON())
    else:
        manejador.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s %(name)s | %(message)s")
        )

    raiz = logging.getLogger()
    raiz.handlers = [manejador]
    raiz.setLevel(level.upper())

    # Los loggers de uvicorn propagan a la raíz en vez de escribir por su cuenta, para que
    # todo salga con el mismo formato. `uvicorn.access` se silencia porque el middleware de
    # `request_logging.py` registra lo mismo con más contexto y en JSON.
    for nombre in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(nombre)
        logger.handlers = []
        logger.propagate = True

    logging.getLogger("uvicorn.access").disabled = True
