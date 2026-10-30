"""Apoyo de las pruebas de infraestructura: compilar plantillas y recorrer el ARM resultante.

Las pruebas no despliegan nada ni necesitan sesión de Azure. Compilan cada plantilla con
`az bicep build` y comprueban el ARM que saldría hacia Azure: lo que se va a desplegar de verdad,
no lo que el Bicep parece decir.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

AZURE = Path(__file__).resolve().parent.parent
BICEP = AZURE / "bicep"
MODULOS = BICEP / "modules"
PARAMETROS = BICEP / "parametros"
SCRIPTS = AZURE / "scripts"

# Qué plantilla consume cada archivo de parámetros. `etiquetas.json` acompaña a TODOS los
# despliegues: lo que declara tiene que existir en las tres plantillas de entrada.
PLANTILLA_DE_PERFIL = {
    "economico.json": "main.bicep",
    "demo.json": "main.bicep",
    "base.json": "base.bicep",
    "suscripcion.json": "suscripcion.bicep",
}
PARAMETROS_COMUNES = "etiquetas.json"

# Valores que define el equipo y que el documento prohíbe inventar (sección 14).
PENDIENTES_DEL_EQUIPO = {
    "dueno",
    "centroCosto",
    "correosAlertas",
    "montoPresupuesto",
    "inicioPresupuesto",
    "correosPresupuesto",
}


def _az() -> str:
    az = shutil.which("az")
    if az is None:
        raise RuntimeError("az no está instalado: las pruebas compilan con `az bicep build`")
    return az


@lru_cache(maxsize=None)
def compilar(relativa: str) -> dict[str, Any]:
    """ARM compilado de una plantilla, relativa a `bicep/`. Se compila una vez por proceso.

    Compila a un ARCHIVO y no a la salida estándar: en Windows, `az` escribe la salida en la
    codificación de la consola (cp1252), y las tildes de las descripciones la vuelven ilegible
    como UTF-8. El archivo lo escribe `bicep`, siempre en UTF-8.
    """
    ruta = BICEP / relativa
    with tempfile.TemporaryDirectory() as carpeta:
        salida = Path(carpeta) / "plantilla.json"
        resultado = subprocess.run(
            [_az(), "bicep", "build", "--file", str(ruta), "--outfile", str(salida)],
            capture_output=True,
            check=False,
        )
        if resultado.returncode != 0:
            error = resultado.stderr.decode("utf-8", errors="replace")
            raise AssertionError(f"{relativa} no compila:\n{error}")
        return json.loads(salida.read_text(encoding="utf-8"))


def recursos(plantilla: dict[str, Any], ruta: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    """Todos los recursos que se DESPLIEGAN, entrando en los módulos anidados.

    Devuelve `(ruta, recurso)`, donde la ruta es la cadena de módulos hasta él. Los `existing` no
    se cuentan: no crean nada. Admite las dos formas del ARM compilado: la lista clásica y el
    diccionario por nombre simbólico de `languageVersion 2.0`.
    """
    contenido = plantilla.get("resources", [])
    elementos = contenido.items() if isinstance(contenido, dict) else enumerate(contenido)
    for simbolo, recurso in elementos:
        if recurso.get("existing"):
            continue
        if recurso["type"] == "Microsoft.Resources/deployments":
            anidada = recurso["properties"]["template"]
            yield from recursos(anidada, f"{ruta}/{simbolo}")
        else:
            yield f"{ruta}/{simbolo}", recurso


def de_tipo(plantilla: dict[str, Any], tipo: str) -> list[dict[str, Any]]:
    return [r for _, r in recursos(plantilla) if r["type"].lower() == tipo.lower()]


def plantilla_de_modulo(plantilla: dict[str, Any], simbolo: str) -> dict[str, Any]:
    """La plantilla anidada de un módulo, a cualquier profundidad.

    Se busca por nombre simbólico y, si no, por el nombre del despliegue: un módulo que no
    importa nada compila al ARM clásico, donde los recursos son una lista sin símbolos.
    """
    contenido = plantilla.get("resources", {})
    elementos = contenido.items() if isinstance(contenido, dict) else enumerate(contenido)
    for nombre, recurso in elementos:
        if recurso.get("type") != "Microsoft.Resources/deployments":
            continue
        anidada = recurso["properties"]["template"]
        if simbolo in (nombre, recurso.get("name")):
            return anidada
        try:
            return plantilla_de_modulo(anidada, simbolo)
        except KeyError:
            continue
    raise KeyError(simbolo)


def leer_parametros(nombre: str) -> dict[str, Any]:
    with open(PARAMETROS / nombre, encoding="utf-8") as archivo:
        return json.load(archivo)["parameters"]


def valor(parametro: dict[str, Any]) -> Any:
    return parametro.get("value")


def pendientes() -> list[tuple[str, str]]:
    """Los valores del equipo que siguen vacíos: `(archivo, parámetro)`."""
    faltan = []
    for archivo in sorted(p.name for p in PARAMETROS.glob("*.json")):
        for nombre, parametro in leer_parametros(archivo).items():
            if nombre in PENDIENTES_DEL_EQUIPO and valor(parametro) in ("", [], 0, None):
                faltan.append((archivo, nombre))
    return faltan


def bash() -> str | None:
    """El bash de Git en Windows o el del sistema. En Windows 11 el `bash` del PATH es el lanzador
    de WSL, que sin distribución instalada no ejecuta nada."""
    if os.name == "nt":
        git = Path(r"C:\Program Files\Git\bin\bash.exe")
        return str(git) if git.exists() else None
    return shutil.which("bash")
