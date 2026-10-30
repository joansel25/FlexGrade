# shellcheck shell=bash
# ---------------------------------------------------------------------------
# Publicar la SPA en el sitio estatico de la cuenta que crea `bicep/modules/borde/frontend.bicep`.
#
# Activar el sitio estatico NO SE PUEDE DESDE BICEP: es una propiedad del plano de datos, no de
# ARM. Por eso vive aqui y no en la plantilla.
# ---------------------------------------------------------------------------
# shellcheck disable=SC2154

# Recibe el nombre de la cuenta de almacenamiento.
publicar_frontend() {
  local cuenta="$1" url

  if [ ! -d "$RAIZ/frontend/dist" ]; then
    gris "no hay frontend/dist; construyendo"
    ( cd "$RAIZ/frontend" && npm run build )
  fi

  # El documento 404 apunta tambien a index.html porque React Router resuelve las rutas en el
  # navegador: sin eso, recargar estando en /matricula da un 404 del almacenamiento.
  az storage blob service-properties update --account-name "$cuenta" \
    --static-website --index-document index.html \
    --404-document index.html --output none

  # Las comillas simples de '$web' son DELIBERADAS: ese es el nombre literal del contenedor que
  # Azure usa para los sitios estaticos, con el dolar incluido. Expandirlo lo dejaria vacio.
  # shellcheck disable=SC2016
  az storage blob upload-batch --account-name "$cuenta" \
    --source "$(ruta_nativa "$RAIZ/frontend/dist")" --destination '$web' --overwrite --output none

  url="$(salida_despliegue urlFrontend)"
  # CORS se aplica DESPUES de conocer la URL, que no existe hasta que la cuenta esta creada.
  # Sin esto el navegador bloquea todas las llamadas y la aplicacion se ve, pero no funciona.
  az webapp config appsettings set --resource-group "$GRUPO" --name "$(salida_despliegue nombreApp)" \
    --settings "CORS_ALLOWED_ORIGINS=${url%/}" --output none
  verde "publicado y autorizado en CORS"
}
