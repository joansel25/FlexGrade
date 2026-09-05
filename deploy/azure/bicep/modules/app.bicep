/*
  App Service para contenedores: el plan, la aplicación y su identidad.

  EL ORDEN DE ESTE ARCHIVO ES LO MÁS IMPORTANTE QUE TIENE

  La aplicación lee sus secretos con referencias `@Microsoft.KeyVault(SecretUri=...)`, y para
  resolverlas necesita que su identidad administrada tenga permiso sobre el almacén. Pero la
  identidad no existe hasta que la aplicación se crea. Si la configuración se aplicara a la vez
  que la aplicación, el App Service arrancaría, no podría resolver las referencias y guardaría
  la CADENA LITERAL `@Microsoft.KeyVault(...)` como valor de `DATABASE_URL`.

  El síntoma es el peor posible: la aplicación falla al conectarse con un error de PostgreSQL
  sobre una URL malformada, y en ningún momento se menciona el Key Vault ni los permisos.

  Por eso la configuración va en un recurso APARTE que depende del permiso:

      1. plan
      2. aplicación (con identidad administrada, sin ajustes todavía)
      3. permisos sobre el Key Vault y el ACR   <- en otro módulo, otro grupo de recursos
      4. ajustes de la aplicación                <- solo cuando el permiso existe

  Este archivo cubre SOLO los pasos 1 y 2. El 3 lo hace `permisos.bicep`, sobre el grupo
  persistente, y el 4 lo hace `ajustes.bicep`.

  La separación no es estética: la primera versión metía los ajustes aquí con un `dependsOn`
  hacia los permisos, y el compilador la rechazó por un ciclo —`app -> permisos -> app`— que era
  real. Los permisos necesitan la identidad, que no existe hasta que la aplicación se crea.
*/

@description('Región.')
param ubicacion string

@description('Prefijo de los nombres.')
param prefijo string

@description('Sufijo único global: el nombre del App Service se publica en azurewebsites.net.')
param sufijo string

@description('SKU del plan. `B1` no admite autoescalado ni pasa de 3 instancias; `S1` es el que exige la sección 5 del documento.')
@allowed(['B1', 'S1'])
param skuPlan string = 'S1'

@description('Instancias con las que arranca. El autoescalado, si lo hay, las mueve después.')
@minValue(1)
param instancias int = 1

@description('Subred delegada donde se integra la aplicación para salir a la red privada.')
param subredAppId string

@description('Servidor de inicio de sesión del ACR persistente.')
param acrLoginServer string

@description('Etiqueta de la imagen que se va a ejecutar. El pipeline la sustituye por `dev-<sha>` en cada despliegue.')
param etiquetaImagen string = 'latest'

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: '${prefijo}-plan'
  location: ubicacion
  sku: {
    name: skuPlan
    capacity: instancias
  }
  // `reserved: true` es lo que distingue un plan de Linux de uno de Windows. Sin él, el App
  // Service intenta ejecutar la imagen como una aplicación de Windows y falla al arrancar.
  kind: 'linux'
  properties: {
    reserved: true
  }
}

resource aplicacion 'Microsoft.Web/sites@2023-12-01' = {
  name: '${prefijo}-api-${sufijo}'
  location: ubicacion
  kind: 'app,linux,container'
  identity: {
    // Sin secretos que rotar ni que guardar: la identidad la gestiona Azure y muere con la
    // aplicación. Es lo que permite que el ACR no tenga usuario administrador y que la
    // contraseña de PostgreSQL no aparezca en ninguna configuración.
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    // Integración regional con la VNet: es lo que pone la salida de la aplicación dentro de la
    // red privada, y sin lo cual no alcanza ni a PostgreSQL ni a Redis.
    virtualNetworkSubnetId: subredAppId
    siteConfig: {
      linuxFxVersion: 'DOCKER|${acrLoginServer}/matricula-backend:${etiquetaImagen}'
      // Descarga la imagen con la identidad administrada. La alternativa —usuario administrador
      // del ACR— dejaría una contraseña de registro en la configuración de la aplicación.
      acrUseManagedIdentityCreds: true
      // Encamina TODO el tráfico de salida por la VNet, no solo el privado. Es lo que hace que
      // la salida pase por el NAT Gateway y que PostgreSQL vea siempre la misma dirección.
      vnetRouteAllEnabled: true
      // La sonda que mira el balanceador. `/health` y NO `/health/ready`: la segunda comprueba
      // PostgreSQL y Redis, y usarla aquí convertiría una caída momentánea de la base de datos
      // en la retirada de instancias sanas.
      healthCheckPath: '/health'
      alwaysOn: true
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      // Los ajustes NO se declaran aquí. Ver la cabecera del archivo: irían antes de que la
      // identidad tenga permiso, y las referencias al Key Vault quedarían sin resolver.
    }
  }
}

output nombreApp string = aplicacion.name
output hostApp string = aplicacion.properties.defaultHostName
output principalId string = aplicacion.identity.principalId
output planId string = plan.id
output planNombre string = plan.name
