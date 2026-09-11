#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# ¿Hay algo encendido en Azure, y cuanto lleva costando?
#
#   ./deploy/azure/estado.sh
#
# POR QUE ESTE SCRIPT EXISTE
#
# La facturacion de septiembre mostro 114 horas encendido en diez dias —once al dia— en un
# proyecto cuyo modelo entero se basa en que la infraestructura viva por sesiones de tres horas.
# Nadie decidio eso: simplemente no habia forma rapida de saber que seguia viva.
#
# Preguntarlo tenia que costar menos que ir al portal. Esto responde en dos segundos.
# ---------------------------------------------------------------------------

source "$(dirname "${BASH_SOURCE[0]}")/_comun.sh"

comprobar_az

titulo "Grupo efimero: $GRUPO"

if ! existe_grupo "$GRUPO"; then
  verde "  APAGADO. No se esta gastando nada."
else
  cuantos="$(az resource list --resource-group "$GRUPO" --query "length(@)" -o tsv 2>/dev/null || echo "?")"

  if az network application-gateway show --resource-group "$GRUPO" --name matricula-gateway \
       --query name -o tsv >/dev/null 2>&1; then
    tarifa="$COSTE_HORA_DEMO"; cual="demostracion"
  else
    tarifa="$COSTE_HORA_ECONOMICO"; cual="economico"
  fi

  rojo "  ENCENDIDO  ·  $cuantos recursos  ·  perfil $cual  ·  ~$tarifa USD/hora"

  horas="$(horas_encendido)"
  if [ -n "$horas" ]; then
    gasto="$(python -c "print(f'{float('''$horas''') * float('''$tarifa'''):.2f}')")"
    dia="$(python -c "print(f'{float('''$tarifa''') * 24:.2f}')")"
    printf '  Lleva      %s horas  ->  ~%s USD gastados\n' "$horas" "$gasto"
    printf '  Si se deja %s USD al dia\n' "$dia"
  fi

  app="$(az deployment group show --resource-group "$GRUPO" --name "$DESPLIEGUE" \
         --query properties.outputs.urlApp.value -o tsv 2>/dev/null || true)"
  [ -n "$app" ] && printf '  API        %s\n' "$app"

  # El plan puede tener mas instancias de las que se desplegaron si el autoescalado actuo. Es el
  # numero que de verdad se esta pagando, y el que interesa mirar mientras se genera carga.
  inst="$(az appservice plan show --resource-group "$GRUPO" --name matricula-plan \
          --query "{n:sku.capacity, s:sku.name}" -o tsv 2>/dev/null || true)"
  [ -n "$inst" ] && printf '  Plan       %s instancias (%s)\n' $inst

  printf '\n'
  aviso "  Para apagarlo:  ./deploy/azure/destruir.sh"
fi

# --- el grupo persistente --------------------------------------------------

titulo "Grupo persistente: $GRUPO_BASE"
if existe_grupo "$GRUPO_BASE"; then
  gris "  Presente (~5 USD/mes). Key Vault y registro de contenedores. Nunca se borra."
  etiquetas="$(az acr repository show-tags --name "$(parametro "$BICEP/parametros.economico.json" nombreAcr)" \
               --repository matricula-backend -o tsv 2>/dev/null | tr '\n' ' ' || true)"
  if [ -n "$etiquetas" ]; then
    gris "  Imagenes: $etiquetas"
  else
    aviso "  Sin imagen subida: el proximo levantar.sh la construira (necesita Docker)."
  fi
else
  rojo "  NO EXISTE. Hay que rehacerlo con bicep/base.bicep antes de poder desplegar nada."
fi
