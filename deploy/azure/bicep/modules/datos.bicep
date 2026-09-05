/*
  Datos: PostgreSQL Flexible Server y Azure Cache for Redis, los dos en la red privada.

  LO QUE MÁS TARDA DE TODO EL DESPLIEGUE. Redis ronda los veinte minutos y PostgreSQL con alta
  disponibilidad otros quince. Se declaran en el mismo módulo para que Bicep los cree EN
  PARALELO —no dependen uno del otro—, lo que convierte treinta y cinco minutos en veinte.

  LAS DOS ZONAS DNS PRIVADAS NO SON OPCIONALES

  Es el fallo más común de este montaje y no da la cara hasta que la aplicación intenta
  conectarse. Sin la zona privada, el nombre del servidor resuelve a su dirección PÚBLICA, que
  está deshabilitada, y el error que se ve es un tiempo de espera agotado que no menciona el DNS
  por ningún lado. Con ella, el mismo nombre resuelve a la dirección privada de la VNet.
*/

@description('Región donde se crea todo.')
param ubicacion string

@description('Prefijo de los nombres.')
param prefijo string

@description('Sufijo único global. Los nombres de PostgreSQL y Redis se resuelven por DNS público y no pueden repetirse en todo Azure.')
param sufijo string

@description('Identificador de la VNet, para enlazar las zonas DNS privadas.')
param vnetId string

@description('Subred delegada donde se inyecta PostgreSQL.')
param subredDatosId string

@description('Subred donde aterriza el punto de conexión privado de Redis.')
param subredEndpointsId string

@description('Usuario administrador de PostgreSQL.')
param usuarioAdmin string

@description('Contraseña del administrador. Llega del Key Vault persistente, nunca escrita en un archivo de parámetros.')
@secure()
param claveAdmin string

@description('SKU de PostgreSQL. La alta disponibilidad NO existe en el nivel Burstable (B1ms): exige General Purpose o superior.')
param skuPostgres string = 'Standard_D2ds_v4'

@description('Nivel del SKU. `Burstable` es el barato y no admite standby; `GeneralPurpose` es el que el documento pide.')
@allowed(['Burstable', 'GeneralPurpose', 'MemoryOptimized'])
param nivelPostgres string = 'GeneralPurpose'

@description('Alta disponibilidad con réplica en otra zona. Solo se puede activar si el nivel es GeneralPurpose o superior.')
param altaDisponibilidad bool = true

@description('Grupo de recursos persistente, donde vive el Key Vault.')
param grupoBase string

@description('Nombre del Key Vault persistente.')
param nombreKeyVault string

var nombreServidor = '${prefijo}-pg-${sufijo}'
var nombreRedis = '${prefijo}-redis-${sufijo}'

// ---------------------------------------------------------------------------
// PostgreSQL Flexible Server, inyectado en la VNet
// ---------------------------------------------------------------------------

// El nombre de la zona para el acceso privado de Flexible Server TIENE que terminar en
// `.private.postgres.database.azure.com`. Con cualquier otro sufijo, Azure rechaza el
// despliegue del servidor.
resource zonaDnsPostgres 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: '${prefijo}.private.postgres.database.azure.com'
  location: 'global'
}

resource enlaceDnsPostgres 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: zonaDnsPostgres
  name: 'enlace-vnet'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnetId }
    // Sin registro automático: las entradas de esta zona las crea el propio servidor.
    registrationEnabled: false
  }
}

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2022-12-01' = {
  name: nombreServidor
  location: ubicacion
  sku: {
    name: skuPostgres
    tier: nivelPostgres
  }
  properties: {
    version: '16'
    administratorLogin: usuarioAdmin
    administratorLoginPassword: claveAdmin
    storage: {
      // El mínimo. Los datos de una matrícula caben de sobra, y el almacenamiento se puede
      // aumentar en caliente pero NUNCA reducir: empezar grande es una decisión irreversible.
      storageSizeGB: 32
    }
    backup: {
      // Siete días entran en el precio del servidor. Es lo que permite una restauración a un
      // punto en el tiempo si una migración sale mal.
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    // El «standby» de la sección 2 del documento. La réplica vive en OTRA zona de
    // disponibilidad y usa la misma subred delegada: no hay que reservarle nada.
    highAvailability: {
      mode: altaDisponibilidad ? 'ZoneRedundant' : 'Disabled'
    }
    network: {
      delegatedSubnetResourceId: subredDatosId
      privateDnsZoneArmResourceId: zonaDnsPostgres.id
      // `publicNetworkAccess` NO se declara aquí a propósito. Al inyectar el servidor en una
      // subred delegada, Azure cierra el acceso público por su cuenta, y fijarlo además puede
      // rechazar el despliegue por propiedades en conflicto. Lo que decide quién entra es la
      // red, no una regla de firewall por dirección.
    }
  }
  dependsOn: [enlaceDnsPostgres]
}

resource baseDeDatos 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2022-12-01' = {
  parent: postgres
  name: 'matricula'
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

// La extensión `pgcrypto` la usan las migraciones para `gen_random_uuid()`, y `unaccent` la
// búsqueda del catálogo. En Flexible Server hay que declararlas permitidas ANTES de que
// `CREATE EXTENSION` funcione: sin esto, la migración 0002 falla con un permiso denegado.
resource extensionesPermitidas 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2022-12-01' = {
  parent: postgres
  name: 'azure.extensions'
  properties: {
    value: 'PGCRYPTO,UNACCENT'
    source: 'user-override'
  }
}

// ---------------------------------------------------------------------------
// Azure Cache for Redis con punto de conexión privado
// ---------------------------------------------------------------------------

resource redis 'Microsoft.Cache/redis@2023-08-01' = {
  name: nombreRedis
  location: ubicacion
  properties: {
    sku: {
      // Basic C0: 250 MB, sin réplica. Suficiente para el catálogo y los contadores del
      // limitador, que son datos que se pueden perder sin consecuencias —el catálogo se relee
      // de PostgreSQL y el límite se reinicia—.
      //
      // La inyección en VNet que insinúa el documento solo existe en el nivel Premium, que
      // cuesta quince veces más. El punto de conexión privado consigue lo mismo que importa:
      // que solo se llegue desde dentro de la red.
      name: 'Basic'
      family: 'C'
      capacity: 0
    }
    // El 6379 sin cifrar se queda cerrado. Es lo que obliga a que `REDIS_URL` sea `rediss://`
    // y por el 6380, y no lo que dice la sección 4 del documento.
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
    publicNetworkAccess: 'Disabled'
  }
}

resource zonaDnsRedis 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.redis.cache.windows.net'
  location: 'global'
}

resource enlaceDnsRedis 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: zonaDnsRedis
  name: 'enlace-vnet'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnetId }
    registrationEnabled: false
  }
}

resource endpointRedis 'Microsoft.Network/privateEndpoints@2023-09-01' = {
  name: '${prefijo}-pe-redis'
  location: ubicacion
  properties: {
    subnet: { id: subredEndpointsId }
    privateLinkServiceConnections: [
      {
        name: 'conexion-redis'
        properties: {
          privateLinkServiceId: redis.id
          groupIds: ['redisCache']
        }
      }
    ]
  }
}

// Sin esto el punto de conexión existe pero nadie lo encuentra: es lo que crea el registro A
// dentro de la zona privada.
resource dnsDelEndpoint 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-09-01' = {
  parent: endpointRedis
  name: 'grupo-dns'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'redis'
        properties: { privateDnsZoneId: zonaDnsRedis.id }
      }
    ]
  }
  dependsOn: [enlaceDnsRedis]
}

// ---------------------------------------------------------------------------
// Las cadenas de conexión, directas al Key Vault persistente
// ---------------------------------------------------------------------------
//
// Se componen AQUÍ, que es el único sitio que conoce las dos mitades: el nombre del servidor
// recién creado y la credencial. Y se escriben en el almacén en vez de devolverse como salida,
// porque una salida de despliegue queda en el historial del grupo de recursos y la lee
// cualquiera con permiso de lectura.
//
// `listKeys` sobre Redis devuelve la clave de acceso primaria. Es la única forma de conocerla:
// Azure la genera al crear la instancia y no se puede fijar de antemano.

module secretos 'secretos.bicep' = {
  name: 'secretos'
  scope: resourceGroup(grupoBase)
  params: {
    nombreKeyVault: nombreKeyVault
    databaseUrl: 'postgresql+psycopg://${usuarioAdmin}:${claveAdmin}@${postgres.properties.fullyQualifiedDomainName}:5432/${baseDeDatos.name}?sslmode=require'
    redisUrl: 'rediss://:${redis.listKeys().primaryKey}@${redis.properties.hostName}:${redis.properties.sslPort}/0'
  }
}

// ---------------------------------------------------------------------------
// Salidas
// ---------------------------------------------------------------------------
//
// NO se devuelven cadenas de conexión completas. Una salida de despliegue queda guardada en el
// historial del grupo de recursos y la puede leer cualquiera con permiso de lectura; una
// contraseña ahí dentro es una filtración con fecha indefinida. Se devuelven los nombres, y
// quien componga la cadena va a buscar el secreto al Key Vault.

output postgresNombre string = postgres.name
output postgresHost string = postgres.properties.fullyQualifiedDomainName
output baseDeDatosNombre string = baseDeDatos.name
output redisNombre string = redis.name
output redisHost string = redis.properties.hostName
output redisPuertoTls int = redis.properties.sslPort

// Los identificadores de los secretos, SIN versión: el App Service resuelve siempre el último
// valor, así que tras recrear la infraestructura toma la cadena nueva sin tocar su
// configuración.
output uriSecretoBaseDeDatos string = secretos.outputs.uriBaseDeDatos
output uriSecretoRedis string = secretos.outputs.uriRedis
output uriSecretoJwt string = secretos.outputs.uriJwt
