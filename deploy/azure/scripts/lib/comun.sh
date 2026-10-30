#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
# ---------------------------------------------------------------------------
# Punto de entrada de la libreria: rutas, utilidades basicas y los modulos que usan todos.
#
# No se ejecuta solo: los scripts de `scripts/` hacen `source` de este archivo, y los que
# necesitan algo mas (levantar.sh) cargan ademas sus modulos propios.
#
#   consola.sh   colores, errores y confirmacion por teclado
#   perfil.sh    perfiles de parametros y su coste por hora
#   azure.sh     consultas al grupo de recursos y al despliegue
#   imagen.sh    la imagen del backend en el registro          (solo levantar.sh)
#   despliegue.sh  ensayo, despliegue y comprobacion de salud   (solo levantar.sh)
#   frontend.sh  publicar la SPA en el sitio estatico           (solo levantar.sh)
# ---------------------------------------------------------------------------

# Este archivo define variables que CONSUMEN los demas, y shellcheck no puede saber cuales se
# usan fuera. Sin esto avisaria de media docena de variables «sin usar» que se usan
# constantemente, y ese ruido acabaria haciendo que nadie mire sus avisos.
# shellcheck disable=SC2034

set -euo pipefail

LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS="$(cd "$LIB/.." && pwd)"
AZURE="$(cd "$SCRIPTS/.." && pwd)"
RAIZ="$(cd "$AZURE/../.." && pwd)"
BICEP="$AZURE/bicep"
PARAMETROS="$BICEP/parametros"

# Traduce una ruta de Git Bash (/c/Users/...) a la que entiende un programa de Windows
# (C:/Users/...). En Linux y macOS devuelve la ruta tal cual.
#
# HACE FALTA DE VERDAD. Git Bash convierte las rutas al pasarlas como ARGUMENTOS a un programa
# que no es suyo, pero no cuando van dentro de una cadena —por ejemplo, incrustadas en el fuente
# de un `python -c`—. El sintoma fue un FileNotFoundError sobre un archivo que existe y que
# `ls` encuentra sin problema, que es de los errores que mas cuesta creerse.
ruta_nativa() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -m "$1"
  else
    printf '%s' "$1"
  fi
}

# Multiplica dos numeros con decimales y lo imprime con dos cifras. Bash solo sabe de enteros, y
# las tarifas son de centimos. Los numeros viajan por `sys.argv` y no incrustados en el fuente:
# las horas salen de la salida de `az`, y nada que llegue de fuera debe poder cambiar el programa.
multiplicar() {
  python -c "import sys; print(f'{float(sys.argv[1]) * float(sys.argv[2]):.2f}')" "$1" "$2"
}

source "$LIB/consola.sh"
source "$LIB/perfil.sh"
source "$LIB/azure.sh"
