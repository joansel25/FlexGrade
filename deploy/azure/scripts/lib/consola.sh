# shellcheck shell=bash
# ---------------------------------------------------------------------------
# Salida por consola: colores, errores y confirmacion por teclado.
# ---------------------------------------------------------------------------

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
