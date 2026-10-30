

targetScope = 'resourceGroup'

@description('Nombre del Key Vault persistente.')
param nombreKeyVault string

@description('Cadena de conexión completa a PostgreSQL, con la contraseña dentro.')
@secure()
param databaseUrl string

@description('Cadena de conexión completa a Redis, con la clave de acceso dentro.')
@secure()
param redisUrl string

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: nombreKeyVault
}

resource secretoBaseDeDatos 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'database-url'
  properties: {
    value: databaseUrl
    contentType: 'Cadena de conexión de SQLAlchemy'
  }
}

resource secretoRedis 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'redis-url'
  properties: {
    value: redisUrl
    contentType: 'Cadena de conexión de redis-py'
  }
}

// Se devuelven los identificadores SIN versión (`.../secrets/nombre/`, sin el sufijo de
// versión). Es deliberado: así el App Service resuelve siempre la ÚLTIMA versión, y tras
// recrear la infraestructura la aplicación toma la cadena nueva sin que haya que actualizar su
// configuración. Con una referencia versionada, cada despliegue dejaría a la aplicación
// apuntando a una contraseña que ya no existe.
output uriBaseDeDatos string = '${keyVault.properties.vaultUri}secrets/${secretoBaseDeDatos.name}/'
output uriRedis string = '${keyVault.properties.vaultUri}secrets/${secretoRedis.name}/'
output uriJwt string = '${keyVault.properties.vaultUri}secrets/jwt-secret/'
