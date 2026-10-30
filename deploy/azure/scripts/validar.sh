#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR

# De la libreria solo se usan las rutas y `ruta_nativa`. Nada de lo que carga llama a Azure al
# cargarse, asi que la validacion sigue sin necesitar sesion ni credenciales.
source "$(dirname "${BASH_SOURCE[0]}")/lib/comun.sh"

FALLOS=0

seccion() { printf '\n=== %s ===\n' "$*"; }
mal() { printf 'FALLO: %s\n' "$*" >&2; FALLOS=$((FALLOS + 1)); }

# --- 1. compilar ------------------------------------------------------------

seccion "Compilando las plantillas"

for plantilla in "$BICEP"/*.bicep "$BICEP"/modules/*/*.bicep "$AZURE"/pruebas/politicas/*.bicep; do
  nombre="${plantilla#"$AZURE"/}"
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

# --- 2. las pruebas de la infraestructura ----------------------------------
#
# `deploy/azure/pruebas/` compila cada plantilla y comprueba sobre el ARM lo que exige el
# documento: parametros que encajan, etiquetas en todo, cifrado por tramo, diagnosticos, las seis
# alertas, presupuesto y gobernanza. Solo biblioteca estandar de Python: corre igual en el CI.

seccion "Pruebas de la infraestructura"

if (cd "$AZURE/pruebas" && python -m unittest discover -p 'test_*.py' 2>&1 | sed 's/^/  /'; exit "${PIPESTATUS[0]}"); then
  printf '  ok  pruebas de deploy/azure/pruebas\n'
else
  mal "pruebas de deploy/azure/pruebas"
fi

# --- 2b. lo que falta por decidir --------------------------------------------
#
# AVISO, no fallo: son valores que el documento prohibe inventar y que define el equipo. Sin ellos
# los scripts que despliegan se niegan a arrancar, que es donde importa.

faltan="$(pendientes "$PARAMETROS"/*.json)"
if [ -n "$faltan" ]; then
  seccion "Pendientes del equipo (no impiden validar; si impiden desplegar)"
  printf '%s\n' "$faltan" | sed 's/^/  /'
fi

# --- 3. los scripts ---------------------------------------------------------

seccion "Revisando los scripts"

if command -v shellcheck >/dev/null 2>&1; then
  # La version se imprime porque IMPORTA: una version antigua avisa de menos. Este job fallo una
  # vez por un SC2164 que la imagen `koalaman/shellcheck:stable` no marcaba y la del runner si.
  # Sin este dato, la diferencia entre «pasa en local» y «falla en CI» no tiene explicacion
  # visible.
  printf '  %s\n' "$(shellcheck --version | grep version: | head -1)"

  # `-x` sigue los `source` hasta `lib/`. Sin el, cada variable que un script recibe de la
  # libreria saldria como «sin asignar», y el aviso util quedaria enterrado en ese ruido. Se
  # lanza desde la carpeta de cada archivo porque las directivas `source-path` son relativas.
  for script in "$SCRIPTS"/*.sh "$LIB"/*.sh; do
    nombre="${script#"$SCRIPTS"/}"
    if (cd "$(dirname "$script")" && shellcheck -x "$(basename "$script")"); then
      printf '  ok  %s\n' "$nombre"
    else
      mal "$nombre"
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
