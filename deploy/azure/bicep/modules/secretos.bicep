/*
  Escribe en el Key Vault PERSISTENTE las dos cadenas de conexión que cambian en cada despliegue.

  Se despliega con `scope: resourceGroup(grupoBase)` porque el almacén vive en el otro grupo de
  recursos, el que no se destruye.

  POR QUÉ SOLO DOS SECRETOS Y NO TRES

  `database-url` y `redis-url` apuntan a servidores que se crean de cero cada vez: su nombre y su
  clave son distintos en cada despliegue, así que tiene que escribirlos quien los conoce.

  `jwt-secret` NO se toca. Es la clave con la que se firman las sesiones: regenerarla en cada
  despliegue invalidaría todos los tokens emitidos, y quien tuviera la pestaña abierta se
  quedaría fuera sin explicación. Se crea UNA VEZ a mano en el grupo persistente y sobrevive a
  todos los despliegues:

    az keyvault secret set --vault-name <almacen> --name jwt-secret \
      --value "$(openssl rand -base64 48)"

  POR QUÉ LOS SECRETOS SE ESCRIBEN AQUÍ Y NO SE DEVUELVEN COMO SALIDAS

  Una salida de despliegue queda guardada en el historial del grupo de recursos y la lee
  cualquiera con permiso de lectura. Los parámetros marcados `@secure()` no aparecen ahí.
*/

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
