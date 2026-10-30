# shellcheck shell=bash
# ---------------------------------------------------------------------------
# Ensayar, desplegar y comprobar que lo desplegado responde.
#
# Se despliega SIEMPRE desde el directorio de la plantilla, con rutas relativas. Con una ruta
# absoluta de Git Bash, `--parameters @/c/Users/...` no llega bien: la arroba impide la
# conversion automatica a ruta de Windows y az termina buscando un archivo que no existe.
# ---------------------------------------------------------------------------
# Las variables del perfil las define `cargar_perfil` (perfil.sh) antes de llamar aqui.
# shellcheck disable=SC2154

# Un grupo de recursos VACIO no cuesta nada, asi que `what-if` se puede correr contra Azure de
# verdad —no solo contra el compilador— sin gastar un centimo. Valida la plantilla contra la API
# real y caza lo que el compilador no ve: politicas de la suscripcion, nombres ya ocupados,
# combinaciones de SKU que no existen en la region.
#
# Los `Unsupported` que aparecen NO son errores: son recursos con nombre calculado en tiempo de
# despliegue que la previsualizacion no sabe resolver.
ensayar() {
  (
    cd "$BICEP" || exit 1
    az deployment group what-if \
      --resource-group "$GRUPO" \
      --template-file main.bicep \
      --parameters "@parametros/$PERFIL.json" "@parametros/etiquetas.json" \
      --parameters "vigencia=$(manana)"
  )
}

# Crea el grupo efímero CON SUS ETIQUETAS (12.2), o se las refresca si ya existe.
#
# Las etiquetas del grupo no se heredan solas, y cuando la gobernanza pase a bloquear (13.3), un
# `az group create` sin ellas será rechazado antes de llegar a Bicep. `Vigencia` es mañana: si el
# grupo sigue vivo entonces, alguien se olvidó de destruirlo.
crear_grupo_efimero() {
  local etiquetas
  etiquetas="$(etiquetas_de_grupo "$ETIQUETA_AMBIENTE" "$(manana)")"
  local -a argumentos
  mapfile -t argumentos <<< "$etiquetas"

  if existe_grupo "$GRUPO"; then
    az group update --name "$GRUPO" --tags "${argumentos[@]}" --output none
  else
    az group create --name "$GRUPO" --location "$UBICACION" --tags "${argumentos[@]}" --output none
  fi
}

# Despliega `main.bicep` con el perfil cargado y las etiquetas comunes. Los argumentos extra se
# pasan tal cual a az.
desplegar() {
  (
    cd "$BICEP" || exit 1
    az deployment group create \
      --resource-group "$GRUPO" \
      --template-file main.bicep \
      --parameters "@parametros/$PERFIL.json" "@parametros/etiquetas.json" \
      --parameters "vigencia=$(manana)" \
      "$@" \
      --name "$DESPLIEGUE" \
      --output none
  )
}

# El contenedor de migraciones corre una vez y muere: su codigo de salida es lo unico que dice si
# el esquema quedo escrito.
comprobar_migraciones() {
  [ "$(parametro "$PARAMS" ejecutarMigraciones)" != "False" ] || return 0

  local codigo
  codigo="$(az container show --resource-group "$GRUPO" --name matricula-migraciones \
            --query "containers[0].instanceView.currentState.exitCode" -o tsv 2>/dev/null || echo "?")"
  if [ "$codigo" = "0" ]; then
    verde "migraciones: terminadas con codigo 0"
  else
    aviso "migraciones: codigo '$codigo' — revisa con:"
    aviso "  az container logs --resource-group $GRUPO --name matricula-migraciones"
  fi
}

# Comprobarlo aqui y no dejarlo para el navegador: un despliegue puede terminar en «Succeeded»
# con la aplicacion caida, porque ARM da por buena la creacion del recurso sin mirar si el
# contenedor arranco.
#
# El contenedor arranca en frio: la primera peticion tarda hasta medio minuto, y el App Service
# puede tardar un poco mas en enrutar. Diez intentos de quince segundos cubren de sobra ese
# arranque sin colgarse si algo esta de verdad roto.
esperar_salud() {
  local url listo="no"
  url="$(salida_despliegue urlSalud)"

  for _ in $(seq 1 10); do
    if curl -fsS --max-time 20 "$url" 2>/dev/null | grep -q '"status":"ready"'; then
      listo="si"; break
    fi
    printf '.'
    sleep 15
  done
  printf '\n'

  if [ "$listo" = "si" ]; then
    verde "/health/ready responde: postgres ok, redis ok"
  else
    rojo "/health/ready NO responde como se espera."
    rojo "Sospechosos, en orden: la zona DNS privada no resolvio; la identidad administrada no pudo"
    rojo "leer el Key Vault; o la referencia al secreto quedo sin resolver —en ese caso DATABASE_URL"
    rojo "contiene la cadena literal @Microsoft.KeyVault(...)—. Mira:"
    rojo "  az webapp log tail --resource-group $GRUPO --name $(salida_despliegue nombreApp)"
  fi
}
