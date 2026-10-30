

@description('Región.')
param ubicacion string

@description('Prefijo de los nombres.')
param prefijo string

@description('Etiquetas comunes de la sección 12.2. Las arma `modules/comun/etiquetas.bicep`.')
param tags object

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

import { nombresEfimeros } from '../comun/nombres.bicep'

// Los nombres salen de la función compartida: las alertas del grupo persistente vigilan
// estos recursos por su identificador, calculado con el mismo cálculo.
var nombres = nombresEfimeros(prefijo, sufijo)

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: nombres.plan
  location: ubicacion
  tags: tags
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
  name: nombres.app
  location: ubicacion
  tags: tags
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
