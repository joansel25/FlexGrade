@description('Región.')
param ubicacion string

@description('Prefijo de los nombres.')
param prefijo string

@description('Etiquetas comunes de la sección 12.2. Las arma `modules/comun/etiquetas.bicep`.')
param tags object

@description('Sufijo único global: el nombre de la cuenta de almacenamiento se publica en un dominio público.')
param sufijo string

// ---------------------------------------------------------------------------
// El frontend
// ---------------------------------------------------------------------------
//
// La SPA es HTML, CSS y JavaScript ya compilados: no necesita servidor. Una cuenta de
// almacenamiento con sitio estático cuesta céntimos al mes frente a los 0,095 USD/hora de un
// App Service que solo devolvería archivos.
//
// OJO: activar el sitio estático NO SE PUEDE HACER DESDE BICEP. Es una propiedad del plano de
// datos, no de ARM, así que este módulo crea la cuenta y el paso que la activa y sube el
// `dist/` va en `scripts/lib/frontend.sh`:
//
//   az storage blob service-properties update --account-name <cuenta> \
//     --static-website --index-document index.html --404-document index.html
//   az storage blob upload-batch --account-name <cuenta> -s frontend/dist -d '$web'
//
// El documento 404 apunta también a `index.html` porque React Router resuelve las rutas en el
// navegador: sin eso, recargar la página estando en `/matricula` da un 404 de almacenamiento.

resource almacenamientoWeb 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: '${prefijo}web${sufijo}'
  location: ubicacion
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    // El contenido del sitio estático es público POR DEFINICIÓN: son los archivos que el
    // navegador de cualquiera descarga. No hay nada que proteger aquí, y desactivarlo impediría
    // que el sitio sirviera.
    allowBlobPublicAccess: true
  }
}

output cuentaAlmacenamientoWeb string = almacenamientoWeb.name
// La devuelve el propio recurso. Componerla a mano NO funciona: lleva un número de zona
// (`z19`, `z22`...) que depende de dónde caiga la cuenta y que no se puede saber de antemano.
output urlFrontend string = almacenamientoWeb.properties.primaryEndpoints.web
