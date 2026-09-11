#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Destruye la infraestructura efimera.
#
#   ./deploy/azure/destruir.sh          pregunta antes
#   ./deploy/azure/destruir.sh --si     no pregunta (para encadenarlo)
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

source "$(dirname "${BASH_SOURCE[0]}")/_comun.sh"

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

cuantos="$(az resource list --resource-group "$GRUPO" --query "length(@)" -o tsv 2>/dev/null || echo "?")"
printf '  Recursos   %s\n' "$cuantos"

horas="$(horas_encendido)"
if [ -n "$horas" ]; then
  printf '  Encendido  %s horas\n' "$horas"
  # El perfil no se guarda en ninguna parte, asi que se deduce: si existe el Application Gateway
  # es el de demostracion. Es la diferencia entre 0,071 y 1,03 USD/hora, o sea entre un centimo
  # y un dolar largo — merece la pena distinguirlo en vez de dar una cifra a medias.
  if az network application-gateway show --resource-group "$GRUPO" --name matricula-gateway \
       --query name -o tsv >/dev/null 2>&1; then
    tarifa="$COSTE_HORA_DEMO"; cual="demostracion"
  else
    tarifa="$COSTE_HORA_ECONOMICO"; cual="economico"
  fi
  gasto="$(python -c "print(f'{float('''$horas''') * float('''$tarifa'''):.2f}')")"
  printf '  Perfil     %s (~%s USD/hora)\n' "$cual" "$tarifa"
  printf '  Gastado    ~%s USD en esta sesion\n' "$gasto"
fi

printf '\n'
gris "Los datos de la base de datos se van con el grupo. El siguiente despliegue vuelve a migrar"
gris "y a sembrar, asi que no hay nada que guardar aparte."
gris "Sobreviven: $GRUPO_BASE (Key Vault y registro) y la imagen que ya esta subida."

if [ "$SIN_PREGUNTAR" != "true" ]; then
  printf '\n¿Destruir? [s/N] '
  read -r respuesta
  case "$respuesta" in
    s|S|si|SI|Si) ;;
    *) gris "cancelado"; exit 0 ;;
  esac
fi

# --- adios -----------------------------------------------------------------
#
# `--no-wait` devuelve el control de inmediato. El borrado sigue en Azure y tarda unos diez
# minutos, pero la facturacion se detiene sin esperar a que termine.

az group delete --name "$GRUPO" --yes --no-wait
verde "Borrado en marcha. Tarda unos diez minutos y no hay que esperarlo."

printf '\n'
gris "Comprobar mas tarde:  ./deploy/azure/estado.sh"
