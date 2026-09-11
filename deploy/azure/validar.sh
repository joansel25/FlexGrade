#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Valida la infraestructura como codigo SIN TOCAR AZURE.
#
#   ./deploy/azure/validar.sh
#
# No necesita sesion iniciada, ni credenciales, ni conexion con la suscripcion. Por eso puede
# correr en cada pull request: es el mismo archivo que ejecuta el CI.
#
# QUE COMPRUEBA, Y POR QUE CADA COSA
#
# 1. Que las plantillas COMPILAN, y que no dejan ni un aviso. Los avisos del compilador de Bicep
#    no son ruido: dos de los que salieron en este proyecto eran errores de verdad —una
#    propiedad que en una sonda se llama distinto, y una URL compuesta a mano que lleva un
#    numero de zona impredecible—. Por eso aqui un aviso tumba la validacion.
#
# 2. Que los archivos de parametros ENCAJAN con la plantilla. ARM rechaza un parametro que no
#    existe («The template parameter 'X' is not found») y tambien uno obligatorio que falta, pero
#    lo hace AL DESPLEGAR. Una errata en un nombre se descubriria despues de cuarenta minutos de
#    espera y con medio sistema creado.
#
# 3. Que los scripts de ciclo de vida no tienen fallos evidentes. Los dos errores que aparecieron
#    al ejecutarlos —la confirmacion que se colgaba sin terminal y las rutas de Git Bash— habrian
#    costado lo mismo de encontrar con o sin shellcheck, pero los que vengan despues no.
# ---------------------------------------------------------------------------

set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BICEP="$AQUI/bicep"
FALLOS=0

ruta_nativa() {
  if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi
}

seccion() { printf '\n=== %s ===\n' "$*"; }
mal() { printf 'FALLO: %s\n' "$*" >&2; FALLOS=$((FALLOS + 1)); }

# --- 1. compilar ------------------------------------------------------------

seccion "Compilando las plantillas"

for plantilla in "$BICEP"/*.bicep "$BICEP"/modules/*.bicep; do
  nombre="$(basename "$plantilla")"
  # El compilador escribe los avisos en la salida de error y aun asi termina con codigo 0. Hay
  # que capturarlos y mirarlos: confiar en el codigo de salida deja pasar justo lo que interesa.
  salida="$(az bicep build --file "$(ruta_nativa "$plantilla")" --stdout 2>&1 >/dev/null || true)"
  # El aviso de que hay una version nueva de Bicep no dice nada sobre la plantilla.
  problemas="$(printf '%s' "$salida" | grep -v 'A new Bicep release is available' | grep -E 'Warning|Error' || true)"

  if [ -n "$problemas" ]; then
    mal "$nombre"
    printf '%s\n' "$problemas" | sed 's/^/    /'
  else
    printf '  ok  %s\n' "$nombre"
  fi
done

# --- 2. los parametros contra la plantilla ---------------------------------

seccion "Comprobando los archivos de parametros"

compilado="$BICEP/.main.compilado.json"
az bicep build --file "$(ruta_nativa "$BICEP/main.bicep")" --outfile "$(ruta_nativa "$compilado")" 2>/dev/null

if ! python - "$(ruta_nativa "$compilado")" "$(ruta_nativa "$BICEP")" <<'PY'
import json, io, glob, os, sys

compilado, carpeta = sys.argv[1], sys.argv[2]
plantilla = json.load(io.open(compilado, encoding="utf-8"))
declarados = set(plantilla.get("parameters", {}))
# Un parametro sin `defaultValue` es obligatorio: si no viaja en el archivo, ARM lo pide por
# teclado, y en un script sin teclado eso es un despliegue colgado.
obligatorios = {n for n, d in plantilla["parameters"].items() if "defaultValue" not in d}

problemas = 0
for archivo in sorted(glob.glob(os.path.join(carpeta, "parametros.*.json"))):
    nombre = os.path.basename(archivo)
    try:
        dados = set(json.load(io.open(archivo, encoding="utf-8"))["parameters"])
    except Exception as e:
        print(f"  MAL {nombre}: no se puede leer ({e})")
        problemas += 1
        continue

    sobran = sorted(dados - declarados)
    faltan = sorted(obligatorios - dados)
    if sobran or faltan:
        problemas += 1
        print(f"  MAL {nombre}")
        if sobran:
            print(f"      sobran, ARM los rechaza: {', '.join(sobran)}")
        if faltan:
            print(f"      faltan, son obligatorios: {', '.join(faltan)}")
    else:
        print(f"  ok  {nombre} ({len(dados)} parametros)")

sys.exit(1 if problemas else 0)
PY
then
  mal "los archivos de parametros no encajan con main.bicep"
fi

rm -f "$compilado"

# --- 3. los scripts ---------------------------------------------------------

seccion "Revisando los scripts"

if command -v shellcheck >/dev/null 2>&1; then
  # La version se imprime porque IMPORTA: una version antigua avisa de menos. Este job fallo una
  # vez por un SC2164 que la imagen `koalaman/shellcheck:stable` no marcaba y la del runner si.
  # Sin este dato, la diferencia entre «pasa en local» y «falla en CI» no tiene explicacion
  # visible.
  printf '  %s\n' "$(shellcheck --version | grep version: | head -1)"

  for script in "$AQUI"/*.sh; do
    # SC1091: shellcheck no sigue el `source` de _comun.sh, y no tiene por que.
    if shellcheck --exclude=SC1091 "$script"; then
      printf '  ok  %s\n' "$(basename "$script")"
    else
      mal "$(basename "$script")"
    fi
  done
else
  printf '  shellcheck no esta instalado; se omite (el CI si lo ejecuta)\n'
fi

# --- resultado --------------------------------------------------------------

printf '\n'
if [ "$FALLOS" -eq 0 ]; then
  printf 'Todo correcto. Nada de esto ha tocado Azure ni ha costado nada.\n'
else
  printf '%s comprobacion(es) con fallos.\n' "$FALLOS" >&2
  exit 1
fi
