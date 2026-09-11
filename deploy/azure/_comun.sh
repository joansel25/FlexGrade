#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Lo que comparten levantar.sh, destruir.sh y estado.sh.
#
# No se ejecuta solo: los otros tres hacen `source` de este archivo.
#
# POR QUE LOS NOMBRES SE LEEN DE LOS ARCHIVOS DE PARAMETROS Y NO SE ESCRIBEN AQUI
#
# El Key Vault y el registro de contenedores llevan un sufijo aleatorio que se decidio al crear
# el grupo persistente. Repetirlo en un script mas seria un cuarto sitio donde puede quedar
# desactualizado, y el sintoma de que lo este es un despliegue que falla a los veinte minutos
# por no encontrar un secreto.
# ---------------------------------------------------------------------------

# Este archivo es una libreria: define variables que CONSUMEN los otros tres, y shellcheck no
# puede seguir un `source` para verlo. Sin esto avisaria de media docena de variables «sin usar»
# que se usan constantemente, y ese ruido acabaria haciendo que nadie mire sus avisos.
# shellcheck disable=SC2034

set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "$AQUI/../.." && pwd)"
BICEP="$AQUI/bicep"

GRUPO="${MATRICULA_GRUPO:-matricula-demo}"
GRUPO_BASE="${MATRICULA_GRUPO_BASE:-matricula-base}"
DESPLIEGUE="levantada"

# Coste por hora OBSERVADO, no estimado: sale de la facturacion real de septiembre, donde cuatro
# recursos independientes coincidieron en 114 horas encendido. Se usa para poder decir en voz
# alta lo que lleva gastado una sesion, que es lo unico que evita dejarla encendida sin darse
# cuenta.
COSTE_HORA_ECONOMICO="0.071"
COSTE_HORA_DEMO="1.03"

# El color se apaga solo cuando la salida NO va a una pantalla —una tuberia, un archivo de
# registro, la ventana de un editor—. Alli los codigos de escape no pintan nada: se ven tal cual,
# como un «[90m» pegado delante de cada linea, y ensucian justo lo que se queria leer.
#
# NO_COLOR es la convencion de facto para apagarlo a mano: https://no-color.org
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  _c() { printf '\033[%sm%s\033[0m\n' "$1" "$2"; }
else
  _c() { printf '%s\n' "$2"; }
fi

rojo()   { _c 31 "$*"; }
verde()  { _c 32 "$*"; }
gris()   { _c 90 "$*"; }
aviso()  { _c 33 "$*"; }
titulo() { printf '\n'; _c 1 "$*"; }

morir() { rojo "ERROR: $*" >&2; exit 1; }

# --- comprobaciones previas ------------------------------------------------

comprobar_az() {
  command -v az >/dev/null 2>&1 || morir "az no esta instalado. https://aka.ms/installazurecli"

  if ! az account show >/dev/null 2>&1; then
    morir "no hay sesion de Azure. Ejecuta:  az login"
  fi

  local suscripcion
  suscripcion="$(az account show --query name -o tsv)"
  gris "Suscripcion: $suscripcion"
}

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

# Lee un valor del archivo de parametros. Se usa python y no jq porque jq no viene con Git Bash
# en Windows, y python si esta.
#
# La ruta y la clave viajan por `sys.argv`, no incrustadas en el fuente: asi una ruta con
# espacios o comillas no puede romper el programa ni cambiar lo que hace.
parametro() {
  local archivo clave
  archivo="$(ruta_nativa "$1")"
  clave="$2"
  python -c "
import json, io, sys
d = json.load(io.open(sys.argv[1], encoding='utf-8'))['parameters']
v = d.get(sys.argv[2])
sys.stdout.write('' if v is None else str(v.get('value', '')))
" "$archivo" "$clave"
}

# Valida el perfil y deja las variables del ambiente listas.
cargar_perfil() {
  PERFIL="${1:-economico}"
  case "$PERFIL" in
    economico|demo) ;;
    *) morir "perfil desconocido: '$PERFIL'. Usa 'economico' o 'demo'." ;;
  esac

  PARAMS="$BICEP/parametros.$PERFIL.json"
  [ -f "$PARAMS" ] || morir "no existe $PARAMS"

  UBICACION="$(parametro "$PARAMS" ubicacion)"
  ACR_NOMBRE="$(parametro "$PARAMS" nombreAcr)"
  ACR_SERVIDOR="$(parametro "$PARAMS" acrLoginServer)"
  ETIQUETA="$(parametro "$PARAMS" etiquetaImagen)"
  ETIQUETA="${ETIQUETA:-latest}"

  if [ "$PERFIL" = "demo" ]; then
    COSTE_HORA="$COSTE_HORA_DEMO"
  else
    COSTE_HORA="$COSTE_HORA_ECONOMICO"
  fi
}

# Devuelve las horas que lleva encendido el grupo, o vacio si no hay despliegue.
horas_encendido() {
  local marca
  marca="$(az deployment group show --resource-group "$GRUPO" --name "$DESPLIEGUE" \
           --query properties.timestamp -o tsv 2>/dev/null || true)"
  [ -n "$marca" ] || return 0
  # El calculo va en python: la marca de Azure trae fracciones de segundo y desplazamiento
  # horario, y `date -d` no la digiere igual en todas las maquinas.
  python -c "
from datetime import datetime, timezone
import re, sys
t = re.sub(r'(\.\d{6})\d+', r'\1', '''$marca'''.replace('Z', '+00:00'))
try:
    d = datetime.fromisoformat(t)
except ValueError:
    sys.exit(0)
if d.tzinfo is None:
    d = d.replace(tzinfo=timezone.utc)
print(f'{(datetime.now(timezone.utc) - d).total_seconds() / 3600:.1f}')
"
}

existe_grupo() {
  [ "$(az group exists --name "$1")" = "true" ]
}

# Pide confirmacion por teclado. Devuelve 0 si hay que seguir.
#
# COMPRUEBA PRIMERO QUE HAYA UN TECLADO DETRAS, y no es una precaucion teorica: sin terminal
# —desde un asistente, un pipeline, un `nohup`— un `read` a secas NO devuelve EOF, se queda
# BLOQUEADO PARA SIEMPRE. El script no falla ni avisa: simplemente no termina nunca, y por fuera
# se ve igual que un despliegue lento.
#
# Con `--si` se salta la pregunta. Sin terminal y sin `--si`, se para y lo dice: un script que
# gasta dinero no debe decidir por su cuenta que la respuesta era «adelante».
confirmar() {
  local pregunta="$1" sin_preguntar="${2:-false}"

  [ "$sin_preguntar" = "true" ] && return 0

  if [ ! -t 0 ]; then
    rojo "Hace falta confirmar '$pregunta', pero no hay un terminal donde preguntarlo."
    rojo "Si estas seguro, vuelve a lanzarlo con  --si"
    return 1
  fi

  printf '\n%s [s/N] ' "$pregunta"
  read -r respuesta
  case "$respuesta" in
    s|S|si|SI|Si|sí|SÍ) return 0 ;;
    *) gris "cancelado"; return 1 ;;
  esac
}
