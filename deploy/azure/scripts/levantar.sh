#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR

source "$(dirname "${BASH_SOURCE[0]}")/lib/comun.sh"
# shellcheck source=lib/imagen.sh
source "$LIB/imagen.sh"
# shellcheck source=lib/despliegue.sh
source "$LIB/despliegue.sh"
# shellcheck source=lib/frontend.sh
source "$LIB/frontend.sh"

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
# Antes de tocar Azure: sin `dueno` ni `centroCosto` la plantilla no valida, y es mejor saberlo
# ahora que con el grupo ya creado.
exigir_valores_del_equipo "$ETIQUETAS_COMUNES"
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
  crear_grupo_efimero
else
  titulo "1/5  Creando el grupo '$GRUPO'"
  crear_grupo_efimero
  verde "creado, con sus etiquetas"
fi

# --- 3. el ensayo, si se pidio: ver que saldria sin crear nada -------------
#
# Va ANTES de la imagen a proposito: un ensayo no deberia obligar a tener Docker encendido.

if [ "$ENSAYO" = "true" ]; then
  titulo "2/2  Ensayo: esto es lo que se crearia (sin crear nada)"
  ensayar
  printf '\n'
  verde "Ensayo terminado. No se creo ningun recurso de pago."
  aviso "El grupo '$GRUPO' quedo creado y VACIO, que no cuesta nada. Para quitarlo:"
  aviso "  ./deploy/azure/scripts/destruir.sh"
  exit 0
fi

# --- 4. la imagen ----------------------------------------------------------

titulo "2/5  Comprobando la imagen en el registro"
asegurar_imagen

# --- 5. el despliegue ------------------------------------------------------

titulo "3/5  Desplegando  (unos 40 minutos; es buen momento para un cafe)"

extra=()
if [ "$MODO_PICO" = "true" ]; then
  extra+=(--parameters autoescaladoEnModoDemostracion=true)
fi

arranque="$(date +%s)"
desplegar "${extra[@]}"
verde "desplegado en $(( ($(date +%s) - arranque) / 60 )) minutos"

# --- 6. que de verdad funcione ---------------------------------------------

titulo "4/5  Comprobando que responde"
comprobar_migraciones
esperar_salud

# --- 7. el frontend, solo si hay donde ponerlo ------------------------------

CUENTA="$(salida_despliegue cuentaFrontend)"
if [ -n "$CUENTA" ]; then
  titulo "5/5  Publicando el frontend"
  publicar_frontend "$CUENTA"
else
  gris "5/5  Sin frontend: el perfil economico no crea la cuenta de almacenamiento"
fi

# --- resumen ---------------------------------------------------------------

titulo "Listo"
printf '  API        %s\n' "$(salida_despliegue urlApp)"
[ -n "$(salida_despliegue urlGateway)" ] && printf '  Gateway    %s\n' "$(salida_despliegue urlGateway)"
[ -n "$CUENTA" ] && printf '  Frontend   %s\n' "$(salida_despliegue urlFrontend)"
printf '  Entrar     estudiante01@tdea.edu.co / SecurePass123\n'

printf '\n'
aviso "Corriendo a ~$COSTE_HORA USD/hora. Cuando termines:"
aviso "  ./deploy/azure/scripts/destruir.sh"
