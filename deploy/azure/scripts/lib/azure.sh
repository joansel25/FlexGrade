# shellcheck shell=bash
# ---------------------------------------------------------------------------
# Consultas a Azure que comparten levantar, destruir y estado.
# ---------------------------------------------------------------------------
# shellcheck disable=SC2034

GRUPO="${MATRICULA_GRUPO:-matricula-demo}"
GRUPO_BASE="${MATRICULA_GRUPO_BASE:-matricula-base}"
DESPLIEGUE="levantada"

comprobar_az() {
  command -v az >/dev/null 2>&1 || morir "az no esta instalado. https://aka.ms/installazurecli"

  if ! az account show >/dev/null 2>&1; then
    morir "no hay sesion de Azure. Ejecuta:  az login"
  fi

  local suscripcion
  suscripcion="$(az account show --query name -o tsv)"
  gris "Suscripcion: $suscripcion"
}

existe_grupo() {
  [ "$(az group exists --name "$1")" = "true" ]
}

contar_recursos() {
  az resource list --resource-group "$GRUPO" --query "length(@)" -o tsv 2>/dev/null || echo "?"
}

# Lee una salida del despliegue `levantada`. Vacio si no existe o no se desplego.
salida_despliegue() {
  az deployment group show --resource-group "$GRUPO" --name "$DESPLIEGUE" \
    --query "properties.outputs.$1.value" -o tsv 2>/dev/null || true
}

# Devuelve las horas que lleva encendido el grupo, o vacio si no hay despliegue.
horas_encendido() {
  local marca
  marca="$(az deployment group show --resource-group "$GRUPO" --name "$DESPLIEGUE" \
           --query properties.timestamp -o tsv 2>/dev/null || true)"
  [ -n "$marca" ] || return 0
  # El calculo va en python: la marca de Azure trae fracciones de segundo y desplazamiento
  # horario, y `date -d` no la digiere igual en todas las maquinas.
  python -c "
from datetime import datetime, timezone
import re, sys
t = re.sub(r'(\.\d{6})\d+', r'\1', sys.argv[1].replace('Z', '+00:00'))
try:
    d = datetime.fromisoformat(t)
except ValueError:
    sys.exit(0)
if d.tzinfo is None:
    d = d.replace(tzinfo=timezone.utc)
print(f'{(datetime.now(timezone.utc) - d).total_seconds() / 3600:.1f}')
" "$marca"
}

# Deduce con que perfil se levanto lo que esta encendido y deja `PERFIL_VIVO` y `TARIFA`.
#
# El perfil no se guarda en ninguna parte, asi que se deduce: si existe el Application Gateway
# es el de demostracion. Es la diferencia entre 0,071 y 1,03 USD/hora, o sea entre un centimo
# y un dolar largo — merece la pena distinguirlo en vez de dar una cifra a medias.
detectar_perfil_vivo() {
  if az network application-gateway show --resource-group "$GRUPO" --name matricula-gateway \
       --query name -o tsv >/dev/null 2>&1; then
    TARIFA="$COSTE_HORA_DEMO"; PERFIL_VIVO="demostracion"
  else
    TARIFA="$COSTE_HORA_ECONOMICO"; PERFIL_VIVO="economico"
  fi
}
