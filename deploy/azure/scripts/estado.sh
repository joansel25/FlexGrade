#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
# ---------------------------------------------------------------------------
# ¿Hay algo encendido en Azure, y cuanto lleva costando?
#
#   ./deploy/azure/scripts/estado.sh
#
# POR QUE ESTE SCRIPT EXISTE
#
# La facturacion de septiembre mostro 114 horas encendido en diez dias —once al dia— en un
# proyecto cuyo modelo entero se basa en que la infraestructura viva por sesiones de tres horas.
# Nadie decidio eso: simplemente no habia forma rapida de saber que seguia viva.
#
# Preguntarlo tenia que costar menos que ir al portal. Esto responde en dos segundos.
# ---------------------------------------------------------------------------

source "$(dirname "${BASH_SOURCE[0]}")/lib/comun.sh"

comprobar_az

titulo "Grupo efimero: $GRUPO"

if ! existe_grupo "$GRUPO"; then
  verde "  APAGADO. No se esta gastando nada."
else
  cuantos="$(contar_recursos)"
  detectar_perfil_vivo

  rojo "  ENCENDIDO  ·  $cuantos recursos  ·  perfil $PERFIL_VIVO  ·  ~$TARIFA USD/hora"

  horas="$(horas_encendido)"
  if [ -n "$horas" ]; then
    printf '  Lleva      %s horas  ->  ~%s USD gastados\n' "$horas" "$(multiplicar "$horas" "$TARIFA")"
    printf '  Si se deja %s USD al dia\n' "$(multiplicar "$TARIFA" 24)"
  fi

  app="$(salida_despliegue urlApp)"
  [ -n "$app" ] && printf '  API        %s\n' "$app"

  # El plan puede tener mas instancias de las que se desplegaron si el autoescalado actuo. Es el
  # numero que de verdad se esta pagando, y el que interesa mirar mientras se genera carga.
  #
  # Los dos valores se separan con `IFS` en lugar de dejar que el printf los parta solo: sin
  # comillas, cualquier espacio inesperado en la respuesta descolocaria las columnas.
  instancias=""
  nivel=""
  IFS=$'\t' read -r instancias nivel < <(
    az appservice plan show --resource-group "$GRUPO" --name matricula-plan \
      --query "{n:sku.capacity, s:sku.name}" -o tsv 2>/dev/null || true
  )
  [ -n "$instancias" ] && printf '  Plan       %s instancias (%s)\n' "$instancias" "$nivel"

  printf '\n'
  aviso "  Para apagarlo:  ./deploy/azure/scripts/destruir.sh"
fi

# --- el grupo persistente --------------------------------------------------

titulo "Grupo persistente: $GRUPO_BASE"
if existe_grupo "$GRUPO_BASE"; then
  gris "  Presente (~5 USD/mes). Key Vault y registro de contenedores. Nunca se borra."
  etiquetas="$(az acr repository show-tags --name "$(parametro "$PARAMETROS/economico.json" nombreAcr)" \
               --repository matricula-backend -o tsv 2>/dev/null | tr '\n' ' ' || true)"
  if [ -n "$etiquetas" ]; then
    gris "  Imagenes: $etiquetas"
  else
    aviso "  Sin imagen subida: el proximo scripts/levantar.sh la construira (necesita Docker)."
  fi
else
  rojo "  NO EXISTE. Hay que rehacerlo con bicep/base.bicep antes de poder desplegar nada."
fi
