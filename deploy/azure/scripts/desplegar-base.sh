#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
# ---------------------------------------------------------------------------
# Despliega lo PERSISTENTE: el grupo base y lo que va sobre la suscripción.
#
#   ./deploy/azure/scripts/desplegar-base.sh            despliega
#   ./deploy/azure/scripts/desplegar-base.sh --ensayo   muestra qué cambiaría, sin cambiar nada
#   ./deploy/azure/scripts/desplegar-base.sh --si       no pregunta
#
# EN ESTE ORDEN, Y POR QUÉ
#
#   1. base.bicep         Key Vault, registro, workspace, Application Insights, alertas
#   2. suscripcion.bicep  Registro de actividad, presupuesto, gobernanza: lee el workspace y el
#                         grupo de acciones que crea el paso 1
#
# Va ANTES que `levantar.sh`: la demo lee de aquí Application Insights y el grupo de acciones.
#
# Se lanza cuando cambia algo persistente, no en cada sesión. Cuesta casi nada: lo que tarda es
# el Key Vault, unos segundos.
# ---------------------------------------------------------------------------

source "$(dirname "${BASH_SOURCE[0]}")/lib/comun.sh"

ENSAYO="false"
SIN_PREGUNTAR="false"
for arg in "$@"; do
  case "$arg" in
    --ensayo) ENSAYO="true" ;;
    --si) SIN_PREGUNTAR="true" ;;
    *) morir "opcion desconocida: $arg" ;;
  esac
done

PARAMS_BASE="$PARAMETROS/base.json"
PARAMS_SUSCRIPCION="$PARAMETROS/suscripcion.json"
UBICACION="$(parametro "$PARAMS_BASE" ubicacion)"

# Antes de tocar Azure: el documento prohíbe inventar estos valores, y sin ellos las plantillas
# no validan.
exigir_valores_del_equipo "$ETIQUETAS_COMUNES" "$PARAMS_BASE" "$PARAMS_SUSCRIPCION"
comprobar_az

# --- 0. lo que hay que saber antes de seguir --------------------------------

if [ "$ENSAYO" != "true" ]; then
  titulo "Antes de desplegar"
  aviso "El Key Vault pasa a RBAC: tu cuenta deja de poder leer y escribir secretos aunque sea Owner."
  aviso "Para crear o rotar 'jwt-secret' asígnate TEMPORALMENTE 'Key Vault Secrets Officer' (RUNBOOK)."
  if [ "$(parametro "$PARAMS_BASE" protegerPurgaKeyVault)" = "True" ]; then
    aviso "La protección contra purga queda ACTIVADA, y eso es IRREVERSIBLE."
  fi
  if existe_grupo "$GRUPO"; then
    aviso "La demo está encendida: su aplicación lee el almacén con la política antigua. Vuelve a"
    aviso "lanzar levantar.sh después, para que reciba el rol nuevo."
  fi
  confirmar "¿Desplegar el grupo persistente y la suscripción?" "$SIN_PREGUNTAR" || exit 0
fi

# --- 1. el grupo persistente ---------------------------------------------------

titulo "1/2  Grupo persistente '$GRUPO_BASE'"

etiquetas="$(etiquetas_de_grupo compartido)"
mapfile -t argumentos <<< "$etiquetas"
if existe_grupo "$GRUPO_BASE"; then
  az group update --name "$GRUPO_BASE" --tags "${argumentos[@]}" --output none
else
  az group create --name "$GRUPO_BASE" --location "$UBICACION" --tags "${argumentos[@]}" --output none
fi

accion="create"
[ "$ENSAYO" = "true" ] && accion="what-if"

# Desde el directorio de la plantilla, con rutas relativas: con una ruta absoluta de Git Bash,
# la `@` de `--parameters` impide convertirla a ruta de Windows.
(
  cd "$BICEP" || exit 1
  az deployment group "$accion" \
    --resource-group "$GRUPO_BASE" \
    --template-file base.bicep \
    --parameters @parametros/base.json @parametros/etiquetas.json \
    --name base
)

# --- 2. la suscripción ----------------------------------------------------------

titulo "2/2  Suscripción: registro de actividad, presupuesto y gobernanza"

(
  cd "$BICEP" || exit 1
  az deployment sub "$accion" \
    --location "$UBICACION" \
    --template-file suscripcion.bicep \
    --parameters @parametros/suscripcion.json @parametros/etiquetas.json \
    --name flexgrade-suscripcion
)

printf '\n'
if [ "$ENSAYO" = "true" ]; then
  verde "Ensayo terminado. No se cambió nada."
else
  verde "Listo. La gobernanza está en modo '$(parametro "$PARAMS_SUSCRIPCION" modoPoliticas)'."
  gris "Recuerda: 'jwt-secret' no lo escribe Bicep. Ver RUNBOOK."
fi
