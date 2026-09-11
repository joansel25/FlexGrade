#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Levanta la infraestructura completa en Azure.
#
#   ./deploy/azure/levantar.sh                 perfil economico (~0,071 USD/hora)
#   ./deploy/azure/levantar.sh demo            perfil de sustentacion (~1,03 USD/hora)
#   ./deploy/azure/levantar.sh demo --pico     ademas arranca ya en 6 instancias
#   ./deploy/azure/levantar.sh demo --ensayo   muestra que se crearia, sin crear nada (0 USD)
#   ./deploy/azure/levantar.sh demo --si       no pregunta (para lanzarlo sin teclado delante)
#
# TARDA UNOS CUARENTA MINUTOS Y NO BAJA DE AHI. PostgreSQL con replica ronda los quince y Redis
# los veinte; Bicep los crea en paralelo pero no puede acelerarlos. No se lanza cinco minutos
# antes de sustentar.
#
# POR QUE ESTE SCRIPT EXISTE
#
# El runbook ya describe estos pasos, y aun asi la factura de septiembre mostro 114 HORAS
# encendido en diez dias: once al dia. Seguir ocho pasos a mano funciona una vez; lo que no
# funciona es acordarse del ultimo —destruir— cuando ya son las once de la noche. Un comando
# para levantar y otro para destruir es lo que hace que el modelo efimero se cumpla de verdad.
# ---------------------------------------------------------------------------

source "$(dirname "${BASH_SOURCE[0]}")/_comun.sh"

PERFIL_ARG="economico"
MODO_PICO="false"
ENSAYO="false"
SIN_PREGUNTAR="false"
for arg in "$@"; do
  case "$arg" in
    --pico) MODO_PICO="true" ;;
    --ensayo) ENSAYO="true" ;;
    --si) SIN_PREGUNTAR="true" ;;
    -*) morir "opcion desconocida: $arg" ;;
    *) PERFIL_ARG="$arg" ;;
  esac
done

cargar_perfil "$PERFIL_ARG"
comprobar_az

titulo "Perfil: $PERFIL  ·  region: $UBICACION  ·  ~$COSTE_HORA USD/hora"

# --- 1. avisar de lo que cuesta antes de gastarlo --------------------------
#
# La confirmacion solo se pide en el perfil caro. Pedirla siempre entrena a pulsar «s» sin leer,
# que es justo lo que hay que evitar el dia que de verdad importa.

if [ "$PERFIL" = "demo" ] && [ "$ENSAYO" != "true" ]; then
  aviso "El perfil de demostracion incluye Application Gateway con WAF (0,443 USD/hora solo el)"
  aviso "y PostgreSQL GeneralPurpose con replica, que PIERDE la capa gratuita del B1ms."
  aviso "Una sesion de tres horas cuesta unos 3 USD."
  if [ "$MODO_PICO" = "true" ]; then
    aviso "Ademas --pico arranca en 6 instancias: +0,57 USD/hora."
  fi
  confirmar "¿Levantar el perfil de demostracion?" "$SIN_PREGUNTAR" || exit 0
fi

# --- 2. el grupo de recursos ----------------------------------------------

if existe_grupo "$GRUPO"; then
  horas="$(horas_encendido)"
  if [ -n "$horas" ]; then
    aviso "El grupo '$GRUPO' YA EXISTE y lleva $horas h encendido."
    aviso "Volver a desplegar encima no lo destruye ni lo duplica, pero tampoco reinicia el reloj."
  else
    gris "El grupo '$GRUPO' ya existe (sin despliegue previo completo)."
  fi
else
  titulo "1/5  Creando el grupo '$GRUPO'"
  az group create --name "$GRUPO" --location "$UBICACION" --output none
  verde "creado"
fi

# --- 3. el ensayo, si se pidio: ver que saldria sin crear nada -------------
#
# Un grupo de recursos VACIO no cuesta nada, asi que `what-if` se puede correr contra Azure de
# verdad —no solo contra el compilador— sin gastar un centimo. Valida la plantilla contra la API
# real y caza lo que el compilador no ve: politicas de la suscripcion, nombres ya ocupados,
# combinaciones de SKU que no existen en la region.
#
# Va ANTES de la imagen a proposito: un ensayo no deberia obligar a tener Docker encendido.
#
# Los `Unsupported` que aparecen NO son errores: son recursos con nombre calculado en tiempo de
# despliegue que la previsualizacion no sabe resolver.

if [ "$ENSAYO" = "true" ]; then
  titulo "2/2  Ensayo: esto es lo que se crearia (sin crear nada)"
  (
    cd "$BICEP"
    az deployment group what-if \
      --resource-group "$GRUPO" \
      --template-file main.bicep \
      --parameters "@parametros.$PERFIL.json"
  )
  printf '\n'
  verde "Ensayo terminado. No se creo ningun recurso de pago."
  aviso "El grupo '$GRUPO' quedo creado y VACIO, que no cuesta nada. Para quitarlo:"
  aviso "  ./deploy/azure/destruir.sh"
  exit 0
fi

# --- 4. la imagen ----------------------------------------------------------
#
# `az acr build` —que construiria la imagen dentro de Azure— esta BLOQUEADO en la suscripcion de
# estudiante: falla con TasksOperationsNotAllowed. Por eso hace falta Docker local.

titulo "2/5  Comprobando la imagen en el registro"

if az acr repository show-tags --name "$ACR_NOMBRE" --repository matricula-backend \
     --output tsv 2>/dev/null | grep -qx "$ETIQUETA"; then
  verde "matricula-backend:$ETIQUETA ya esta en $ACR_NOMBRE (sobrevivio a la destruccion)"
else
  aviso "falta matricula-backend:$ETIQUETA; hay que construirla y subirla"
  command -v docker >/dev/null 2>&1 || morir "se necesita Docker local: 'az acr build' esta bloqueado en esta suscripcion"
  docker info >/dev/null 2>&1 || morir "Docker esta instalado pero no esta corriendo"

  az acr login --name "$ACR_NOMBRE"
  docker build --tag "$ACR_SERVIDOR/matricula-backend:$ETIQUETA" --target runtime "$(ruta_nativa "$RAIZ/backend")"
  docker push "$ACR_SERVIDOR/matricula-backend:$ETIQUETA"
  verde "subida"
fi

# --- 5. el despliegue ------------------------------------------------------

titulo "3/5  Desplegando  (unos 40 minutos; es buen momento para un cafe)"

extra=()
if [ "$MODO_PICO" = "true" ]; then
  extra+=(--parameters autoescaladoEnModoDemostracion=true)
fi

arranque="$(date +%s)"
# Se despliega DESDE el directorio de la plantilla, con rutas relativas. Con una ruta absoluta de
# Git Bash, `--parameters @/c/Users/...` no llega bien: la arroba impide la conversion automatica
# a ruta de Windows y az termina buscando un archivo que no existe.
(
  cd "$BICEP"
  az deployment group create \
    --resource-group "$GRUPO" \
    --template-file main.bicep \
    --parameters "@parametros.$PERFIL.json" \
    "${extra[@]}" \
    --name "$DESPLIEGUE" \
    --output none
)
verde "desplegado en $(( ($(date +%s) - arranque) / 60 )) minutos"

salida() {
  az deployment group show --resource-group "$GRUPO" --name "$DESPLIEGUE" \
    --query "properties.outputs.$1.value" -o tsv 2>/dev/null || true
}

# --- 6. que de verdad funcione ---------------------------------------------
#
# Comprobarlo aqui y no dejarlo para el navegador: un despliegue puede terminar en «Succeeded»
# con la aplicacion caida, porque ARM da por buena la creacion del recurso sin mirar si el
# contenedor arranco.

titulo "4/5  Comprobando que responde"

if [ "$(parametro "$PARAMS" ejecutarMigraciones)" != "False" ]; then
  estado_mig="$(az container show --resource-group "$GRUPO" --name matricula-migraciones \
                --query "containers[0].instanceView.currentState.exitCode" -o tsv 2>/dev/null || echo "?")"
  if [ "$estado_mig" = "0" ]; then
    verde "migraciones: terminadas con codigo 0"
  else
    aviso "migraciones: codigo '$estado_mig' — revisa con:"
    aviso "  az container logs --resource-group $GRUPO --name matricula-migraciones"
  fi
fi

URL_SALUD="$(salida urlSalud)"
listo="no"
# El contenedor arranca en frio: la primera peticion tarda hasta medio minuto, y el App Service
# puede tardar un poco mas en enrutar. Diez intentos de quince segundos cubren de sobra ese
# arranque sin colgarse si algo esta de verdad roto.
for _ in $(seq 1 10); do
  if curl -fsS --max-time 20 "$URL_SALUD" 2>/dev/null | grep -q '"status":"ready"'; then
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
  rojo "  az webapp log tail --resource-group $GRUPO --name $(salida nombreApp)"
fi

# --- 7. el frontend, solo si hay donde ponerlo ------------------------------
#
# Activar el sitio estatico NO SE PUEDE DESDE BICEP: es una propiedad del plano de datos, no de
# ARM. Por eso vive aqui y no en la plantilla.

CUENTA="$(salida cuentaFrontend)"
if [ -n "$CUENTA" ]; then
  titulo "5/5  Publicando el frontend"

  if [ ! -d "$RAIZ/frontend/dist" ]; then
    gris "no hay frontend/dist; construyendo"
    ( cd "$RAIZ/frontend" && npm run build )
  fi

  az storage blob service-properties update --account-name "$CUENTA" \
    --static-website --index-document index.html \
    --404-document index.html --output none
  # El documento 404 apunta tambien a index.html porque React Router resuelve las rutas en el
  # navegador: sin eso, recargar estando en /matricula da un 404 del almacenamiento.

  # Las comillas simples de '$web' son DELIBERADAS: ese es el nombre literal del contenedor que
  # Azure usa para los sitios estaticos, con el dolar incluido. Expandirlo lo dejaria vacio.
  # shellcheck disable=SC2016
  az storage blob upload-batch --account-name "$CUENTA" \
    --source "$(ruta_nativa "$RAIZ/frontend/dist")" --destination '$web' --overwrite --output none

  URL_FRONT="$(salida urlFrontend)"
  # CORS se aplica DESPUES de conocer la URL, que no existe hasta que la cuenta esta creada.
  # Sin esto el navegador bloquea todas las llamadas y la aplicacion se ve, pero no funciona.
  az webapp config appsettings set --resource-group "$GRUPO" --name "$(salida nombreApp)" \
    --settings "CORS_ALLOWED_ORIGINS=${URL_FRONT%/}" --output none
  verde "publicado y autorizado en CORS"
else
  gris "5/5  Sin frontend: el perfil economico no crea la cuenta de almacenamiento"
fi

# --- resumen ---------------------------------------------------------------

titulo "Listo"
printf '  API        %s\n' "$(salida urlApp)"
[ -n "$(salida urlGateway)" ] && printf '  Gateway    %s\n' "$(salida urlGateway)"
[ -n "$CUENTA" ] && printf '  Frontend   %s\n' "$(salida urlFrontend)"
printf '  Entrar     estudiante01@tdea.edu.co / SecurePass123\n'

printf '\n'
aviso "Corriendo a ~$COSTE_HORA USD/hora. Cuando termines:"
aviso "  ./deploy/azure/destruir.sh"
