#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
# ---------------------------------------------------------------------------
# Destruye la infraestructura efimera.
#
#   ./deploy/azure/scripts/destruir.sh          pregunta antes
#   ./deploy/azure/scripts/destruir.sh --si     no pregunta (para encadenarlo)
#
# Tarda unos diez minutos y NO hay que esperarlo: el gasto deja de contar casi de inmediato.
#
# LO QUE NUNCA SE BORRA
#
# `matricula-base`, donde viven el Key Vault y el registro de contenedores. El Key Vault tiene
# borrado logico de 90 dias: si se destruyera, su NOMBRE quedaria reservado y el siguiente
# despliegue fallaria con «name already in use» sin mencionar en ningun momento que el recurso
# esta en la papelera. Es el fallo que hace que un montaje funcione una vez y a la siguiente no.
#
# Por eso el script se niega explicitamente a tocarlo, aunque se lo pidan por variable de
# entorno. Una comprobacion de mas cuesta una linea; recuperarse de ese borrado cuesta tener que
# cambiar el nombre del almacen en cuatro archivos y esperar tres meses.
# ---------------------------------------------------------------------------

source "$(dirname "${BASH_SOURCE[0]}")/lib/comun.sh"

SIN_PREGUNTAR="false"
[ "${1:-}" = "--si" ] && SIN_PREGUNTAR="true"

comprobar_az

# --- el seguro -------------------------------------------------------------

if [ "$GRUPO" = "$GRUPO_BASE" ]; then
  morir "te estas pidiendo destruir '$GRUPO_BASE', que es el grupo PERSISTENTE. No se hace."
fi

if ! existe_grupo "$GRUPO"; then
  verde "El grupo '$GRUPO' no existe: no hay nada encendido."
  exit 0
fi

# --- que hay dentro y cuanto lleva -----------------------------------------

titulo "Se va a destruir el grupo '$GRUPO'"

printf '  Recursos   %s\n' "$(contar_recursos)"

horas="$(horas_encendido)"
if [ -n "$horas" ]; then
  printf '  Encendido  %s horas\n' "$horas"
  detectar_perfil_vivo
  printf '  Perfil     %s (~%s USD/hora)\n' "$PERFIL_VIVO" "$TARIFA"
  printf '  Gastado    ~%s USD en esta sesion\n' "$(multiplicar "$horas" "$TARIFA")"
fi

printf '\n'
gris "Los datos de la base de datos se van con el grupo. El siguiente despliegue vuelve a migrar"
gris "y a sembrar, asi que no hay nada que guardar aparte."
gris "Sobreviven: $GRUPO_BASE (Key Vault y registro) y la imagen que ya esta subida."

confirmar "¿Destruir '$GRUPO'?" "$SIN_PREGUNTAR" || exit 0

# --- adios -----------------------------------------------------------------
#
# `--no-wait` devuelve el control de inmediato. El borrado sigue en Azure y tarda unos diez
# minutos, pero la facturacion se detiene sin esperar a que termine.

az group delete --name "$GRUPO" --yes --no-wait
verde "Borrado en marcha. Tarda unos diez minutos y no hay que esperarlo."

printf '\n'
gris "Comprobar mas tarde:  ./deploy/azure/scripts/estado.sh"
