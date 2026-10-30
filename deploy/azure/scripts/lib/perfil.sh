# shellcheck shell=bash
# ---------------------------------------------------------------------------
# Los perfiles de despliegue (`bicep/parametros/<perfil>.json`) y lo que cuestan.
#
# POR QUE LOS NOMBRES SE LEEN DE LOS ARCHIVOS DE PARAMETROS Y NO SE ESCRIBEN AQUI
#
# El Key Vault y el registro de contenedores llevan un sufijo aleatorio que se decidio al crear
# el grupo persistente. Repetirlo en un script mas seria un cuarto sitio donde puede quedar
# desactualizado, y el sintoma de que lo este es un despliegue que falla a los veinte minutos
# por no encontrar un secreto.
# ---------------------------------------------------------------------------
# shellcheck disable=SC2034,SC2154

# Coste por hora OBSERVADO, no estimado: sale de la facturacion real de septiembre, donde cuatro
# recursos independientes coincidieron en 114 horas encendido. Se usa para poder decir en voz
# alta lo que lleva gastado una sesion, que es lo unico que evita dejarla encendida sin darse
# cuenta.
COSTE_HORA_ECONOMICO="0.071"
COSTE_HORA_DEMO="1.03"

# Lo que comparten las tres plantillas (las etiquetas `Dueno` y `CentroCosto`). Acompaña a TODOS
# los despliegues como un segundo `--parameters`: un solo sitio para un valor que va en todo.
ETIQUETAS_COMUNES="$PARAMETROS/etiquetas.json"

# Los valores que define el equipo y que el documento prohíbe inventar (sección 14). Es la misma
# lista que `PENDIENTES_DEL_EQUIPO` de `pruebas/apoyo.py`.
PENDIENTES_DEL_EQUIPO="dueno centroCosto correosAlertas montoPresupuesto inicioPresupuesto correosPresupuesto"

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

  PARAMS="$PARAMETROS/$PERFIL.json"
  [ -f "$PARAMS" ] || morir "no existe $PARAMS"

  UBICACION="$(parametro "$PARAMS" ubicacion)"
  ACR_NOMBRE="$(parametro "$PARAMS" nombreAcr)"
  ACR_SERVIDOR="$(parametro "$PARAMS" acrLoginServer)"
  ETIQUETA="$(parametro "$PARAMS" etiquetaImagen)"
  ETIQUETA="${ETIQUETA:-latest}"
  ETIQUETA_AMBIENTE="$(parametro "$PARAMS" etiquetaAmbiente)"

  if [ "$PERFIL" = "demo" ]; then
    COSTE_HORA="$COSTE_HORA_DEMO"
  else
    COSTE_HORA="$COSTE_HORA_ECONOMICO"
  fi
}

# Imprime, uno por línea, los valores del equipo que siguen vacíos en los archivos de parámetros
# que se le pasan, como `archivo: parametro`. Vacío si no falta nada.
pendientes() {
  local archivos=()
  local archivo
  for archivo in "$@"; do
    archivos+=("$(ruta_nativa "$archivo")")
  done
  python -c "
import io, json, os, sys
pendientes = set(sys.argv[1].split())
for ruta in sys.argv[2:]:
    datos = json.load(io.open(ruta, encoding='utf-8'))['parameters']
    for nombre, parametro in datos.items():
        if nombre in pendientes and parametro.get('value') in ('', [], 0, None):
            print(f'{os.path.basename(ruta)}: {nombre}')
" "$PENDIENTES_DEL_EQUIPO" "${archivos[@]}"
}

# Se para ANTES de crear nada si falta algún valor del equipo. Azure también los rechazaría
# —las plantillas los declaran con `@minLength(1)`—, pero después de haber creado el grupo.
exigir_valores_del_equipo() {
  local faltan
  faltan="$(pendientes "$@")"
  if [ -n "$faltan" ]; then
    rojo "Faltan valores que define el equipo (sección 14 del documento; no se inventan):"
    printf '%s\n' "$faltan" | sed 's/^/  /' >&2
    morir "rellénalos en bicep/parametros/ y vuelve a lanzarlo"
  fi
}

# Las etiquetas de un GRUPO como argumentos de `az group create --tags`, una por línea. El
# ambiente y la vigencia los decide quien llama: el grupo persistente es `compartido` y no caduca.
etiquetas_de_grupo() {
  local ambiente="$1" vigencia="${2:-}" dueno centro
  dueno="$(parametro "$ETIQUETAS_COMUNES" dueno)"
  centro="$(parametro "$ETIQUETAS_COMUNES" centroCosto)"
  [ -n "$dueno" ] && [ -n "$centro" ] ||
    morir "faltan 'dueno' y 'centroCosto' en bicep/parametros/etiquetas.json"
  printf '%s\n' "Proyecto=FlexGrade" "Dueno=$dueno" "Ambiente=$ambiente" "CentroCosto=$centro"
  [ -z "$vigencia" ] || printf '%s\n' "Vigencia=$vigencia"
}

# La fecha de mañana, AAAA-MM-DD: la `Vigencia` de una sesión (12.2). Si al día siguiente el
# grupo sigue vivo, la etiqueta dice que alguien se olvidó de destruirlo.
manana() {
  python -c "import datetime; print(datetime.date.today() + datetime.timedelta(days=1))"
}
