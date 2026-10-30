#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
# ---------------------------------------------------------------------------
# Pruebas positiva y negativas de la gobernanza (13.3), con evidencia.
#
#   ./deploy/azure/scripts/probar-politicas.sh
#
# NO CREA NINGÚN RECURSO DE PAGO. Cada plantilla de `pruebas/politicas/` se pasa por
# `az deployment group validate`, que evalúa Azure Policy en la validación previa y se detiene
# ahí. Lo único que se crea es un grupo VACÍO y aislado, `matricula-policytest`, que se borra al
# terminar: un grupo vacío no cuesta nada.
#
# SOLO TIENE SENTIDO EN MODO `enforce`. En `audit` la gobernanza no rechaza nada: las pruebas
# negativas «pasarían» y no probarían nada. El script lo comprueba y se niega.
#
# La salida de cada prueba queda en `deploy/azure/evidencias/politicas-<fecha>/`: es la evidencia
# que pide el criterio de cierre de 13.3.
# ---------------------------------------------------------------------------

source "$(dirname "${BASH_SOURCE[0]}")/lib/comun.sh"

GRUPO_PRUEBA="${MATRICULA_GRUPO_POLITICAS:-matricula-policytest}"
PRUEBAS="$AZURE/pruebas/politicas"
EVIDENCIAS="$AZURE/evidencias/politicas-$(date +%Y%m%d-%H%M%S)"

exigir_valores_del_equipo "$ETIQUETAS_COMUNES"
comprobar_az

DUENO="$(parametro "$ETIQUETAS_COMUNES" dueno)"
CENTRO="$(parametro "$ETIQUETAS_COMUNES" centroCosto)"
UBICACION="$(parametro "$PARAMETROS/base.json" ubicacion)"

# --- el seguro: sin bloqueo no hay nada que probar --------------------------

modo="$(az policy assignment show --name flexgrade-gobernanza \
          --query enforcementMode -o tsv 2>/dev/null || true)"
case "$modo" in
  Default) verde "Gobernanza en modo enforce: las pruebas negativas tienen sentido." ;;
  DoNotEnforce) morir "la gobernanza está en modo audit: no rechaza nada y las pruebas no probarían nada. Pasa a enforce primero (13.3)." ;;
  *) morir "no existe la asignación 'flexgrade-gobernanza'. Lanza desplegar-base.sh primero." ;;
esac

if [ "$GRUPO_PRUEBA" = "$GRUPO_BASE" ] || [ "$GRUPO_PRUEBA" = "$GRUPO" ]; then
  morir "el grupo de pruebas no puede ser '$GRUPO_PRUEBA': tiene que ir aislado (13.3)."
fi

# --- el grupo aislado -------------------------------------------------------

titulo "Grupo aislado '$GRUPO_PRUEBA'"
etiquetas="$(etiquetas_de_grupo dev "$(date +%Y-%m-%d)")"
mapfile -t argumentos <<< "$etiquetas"
az group create --name "$GRUPO_PRUEBA" --location "$UBICACION" --tags "${argumentos[@]}" --output none
mkdir -p "$EVIDENCIAS"

FALLOS=0

# Valida una plantilla y comprueba que el resultado es el esperado: `acepta` o `rechaza`.
probar() {
  local plantilla="$1" esperado="$2"
  shift 2
  local salida resultado
  if salida="$(cd "$PRUEBAS" && az deployment group validate \
                 --resource-group "$GRUPO_PRUEBA" \
                 --template-file "$plantilla" \
                 --parameters "$@" 2>&1)"; then
    resultado="acepta"
  elif printf '%s' "$salida" | grep -q "RequestDisallowedByPolicy"; then
    resultado="rechaza"
  else
    resultado="error"
  fi
  printf '%s\n' "$salida" > "$EVIDENCIAS/${plantilla%.bicep}.txt"

  if [ "$resultado" = "$esperado" ]; then
    verde "  ok    $plantilla  ($resultado, como se esperaba)"
  else
    rojo "  FALLO $plantilla  (se esperaba '$esperado' y fue '$resultado')"
    FALLOS=$((FALLOS + 1))
  fi
}

titulo "Pruebas (validación previa, sin crear nada)"
probar nsg-conforme.bicep acepta "dueno=$DUENO" "centroCosto=$CENTRO"
probar nsg-sin-dueno.bicep rechaza "centroCosto=$CENTRO"
probar nsg-ambiente-invalido.bicep rechaza "dueno=$DUENO" "centroCosto=$CENTRO"
# Una contraseña de un solo uso: el servidor no llega a existir, pero la plantilla la exige.
clave="$(python -c "import secrets; print(secrets.token_urlsafe(24) + 'Aa1!')")"
probar postgres-publico.bicep rechaza "dueno=$DUENO" "centroCosto=$CENTRO" "claveDePrueba=$clave"

# --- limpieza ---------------------------------------------------------------

az group delete --name "$GRUPO_PRUEBA" --yes --no-wait
gris "Grupo de pruebas en borrado. Evidencias en: ${EVIDENCIAS#"$RAIZ"/}"

printf '\n'
if [ "$FALLOS" -eq 0 ]; then
  verde "Las cuatro pruebas dieron lo esperado."
else
  morir "$FALLOS prueba(s) no dieron lo esperado. Revisa las evidencias."
fi
