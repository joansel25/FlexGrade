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

// LAS TRES EXTENSIONES QUE USAN LAS MIGRACIONES, y son exactamente tres.
//
// `pgcrypto` para `gen_random_uuid()` (migración 0002), `unaccent` para la búsqueda del catálogo
// (0005) y `btree_gist` para la restricción de exclusión que impide la doble reserva de aulas
// (0010). En Flexible Server hay que declararlas permitidas ANTES de que `CREATE EXTENSION`
// funcione.
//
// La primera versión declaraba solo las dos primeras, y el fallo apareció al desplegar de
// verdad: `extension "btree_gist" is not allow-listed for users`. Ninguna prueba local lo
// habría encontrado —en el PostgreSQL de docker-compose no existe esta lista— y la migración
// que falla es la que sostiene una de las dos defensas del sistema.
resource extensionesPermitidas 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2022-12-01' = {
  parent: postgres
  name: 'azure.extensions'
  properties: {
    value: 'PGCRYPTO,UNACCENT,BTREE_GIST'
    source: 'user-override'
  }
}

// ---------------------------------------------------------------------------
// Azure Cache for Redis con punto de conexión privado
// ---------------------------------------------------------------------------

/*
  AZURE MANAGED REDIS, y no Azure Cache for Redis.

  Lo descubrió el primer despliegue, no la documentación: crear un `Microsoft.Cache/redis` falla
  con «Azure Cache for Redis is retiring, create Azure Managed Redis instance instead». El
  servicio clásico ya no admite instancias nuevas.

  El cambio salió BARATO por casualidad afortunada: el SKU más pequeño de Managed Redis
  —`Balanced_B0`, 0,5 GB— cuesta 0,018 USD/hora frente a los 0,022 del Basic C0 que se retira.
  Consultado en la API de precios de Azure, no estimado.

  Y encima mejora dos cosas que en el servicio viejo costaban dinero:

  - **`highAvailability: Disabled` es una ELECCIÓN aquí**, no una limitación del nivel. En el
    servicio clásico la réplica exigía subir a Standard; aquí se enciende cambiando una palabra.
    Se deja apagada porque lo que guarda Redis en este sistema —el catálogo cacheado y los
    contadores del limitador— se puede perder sin consecuencias: el catálogo se relee de
    PostgreSQL y el límite se reinicia.
  - **El punto de conexión privado sigue siendo la vía**, igual que antes, pero sin que la
    inyección en VNet quede reservada al nivel Premium.
*/
resource redis 'Microsoft.Cache/redisEnterprise@2024-10-01' = {
  name: nombreRedis
  location: ubicacion
  sku: {
    name: 'Balanced_B0'
  }
  properties: {
    // TLS obligatorio. Es lo que hace que `REDIS_URL` empiece por `rediss://` y vaya por el
    // 10000, no por el 6379 sin cifrar que menciona la sección 4 del documento.
    minimumTlsVersion: '1.2'
  }
}

// En Managed Redis la base de datos es un recurso APARTE del clúster, al contrario que en el
// servicio clásico. Sin ella el clúster existe y no acepta una sola conexión.
resource baseRedis 'Microsoft.Cache/redisEnterprise/databases@2024-10-01' = {
  parent: redis
  // El nombre es fijo: Azure solo admite `default`.
  name: 'default'
  properties: {
    clientProtocol: 'Encrypted'
    port: 10000
    evictionPolicy: 'VolatileLRU'
    clusteringPolicy: 'EnterpriseCluster'
  }
}

resource zonaDnsRedis 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  // La zona de Managed Redis es distinta de la del servicio clásico.
  name: 'privatelink.redis.azure.net'
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
          // `redisEnterprise` y no `redisCache`: el grupo depende del tipo de recurso, y con el
          // del servicio viejo el punto de conexión se crea pero no conecta con nada.
          groupIds: ['redisEnterprise']
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
    // La clave la genera Azure al crear la base y se lee de ella, no del clúster. El puerto es
    // el 10000 de Managed Redis, y `/0` porque `redis-py` espera un índice de base lógica.
    redisUrl: 'rediss://:${baseRedis.listKeys().primaryKey}@${redis.properties.hostName}:10000/0'
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
output redisPuertoTls int = 10000

// Los identificadores de los secretos, SIN versión: el App Service resuelve siempre el último
// valor, así que tras recrear la infraestructura toma la cadena nueva sin tocar su
// configuración.
output uriSecretoBaseDeDatos string = secretos.outputs.uriBaseDeDatos
output uriSecretoRedis string = secretos.outputs.uriRedis
output uriSecretoJwt string = secretos.outputs.uriJwt
