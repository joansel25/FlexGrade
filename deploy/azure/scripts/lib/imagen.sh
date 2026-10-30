# shellcheck shell=bash
# ---------------------------------------------------------------------------
# La imagen del backend en el registro persistente.
#
# `az acr build` —que construiria la imagen dentro de Azure— esta BLOQUEADO en la suscripcion de
# estudiante: falla con TasksOperationsNotAllowed. Por eso hace falta Docker local.
# ---------------------------------------------------------------------------
# Las variables del perfil las define `cargar_perfil` (perfil.sh) antes de llamar aqui.
# shellcheck disable=SC2154

# Sube `matricula-backend:$ETIQUETA` solo si no esta ya: el registro sobrevive a la destruccion,
# asi que lo normal es encontrarla.
asegurar_imagen() {
  if az acr repository show-tags --name "$ACR_NOMBRE" --repository matricula-backend \
       --output tsv 2>/dev/null | grep -qx "$ETIQUETA"; then
    verde "matricula-backend:$ETIQUETA ya esta en $ACR_NOMBRE (sobrevivio a la destruccion)"
    return 0
  fi

  aviso "falta matricula-backend:$ETIQUETA; hay que construirla y subirla"
  command -v docker >/dev/null 2>&1 || morir "se necesita Docker local: 'az acr build' esta bloqueado en esta suscripcion"
  docker info >/dev/null 2>&1 || morir "Docker esta instalado pero no esta corriendo"

  az acr login --name "$ACR_NOMBRE"
  docker build --tag "$ACR_SERVIDOR/matricula-backend:$ETIQUETA" --target runtime "$(ruta_nativa "$RAIZ/backend")"
  docker push "$ACR_SERVIDOR/matricula-backend:$ETIQUETA"
  verde "subida"
}
