/*
  AZURE MANAGED REDIS, y no Azure Cache for Redis, con punto de conexión privado.

  Lo descubrió el primer despliegue, no la documentación: crear un `Microsoft.Cache/redis` falla
  con «Azure Cache for Redis is retiring, create Azure Managed Redis instance instead». El
  servicio clásico ya no admite instancias nuevas.

  El SKU más pequeño de Managed Redis —`Balanced_B0`, 0,5 GB— cuesta **0,036 USD/hora**, no
  0,018: la tarifa publicada es POR NODO y el nivel Balanced despliega DOS para poder ofrecer
  alta disponibilidad. Lo confirma la factura (4,09 USD en 114 horas) y el propio Advisor, que
  habla de «2 nodos».

  Es decir: NO salió más barato que el Basic C0 de 0,022 que se retira, sino un 64% más caro.
  A cambio tiene réplica y SLA, que el C0 no tenía. No hay un nivel de un solo nodo.
  Consultado en la API de precios de Azure, no estimado.

  Y mejora dos cosas que en el servicio viejo costaban dinero:

  - **`highAvailability: Disabled` es una ELECCIÓN aquí**, no una limitación del nivel. En el
    servicio clásico la réplica exigía subir a Standard; aquí se enciende cambiando una palabra.
    Se deja apagada porque lo que guarda Redis en este sistema —el catálogo cacheado y los
    contadores del limitador— se puede perder sin consecuencias: el catálogo se relee de
    PostgreSQL y el límite se reinicia.
  - **El punto de conexión privado sigue siendo la vía**, igual que antes, pero sin que la
    inyección en VNet quede reservada al nivel Premium.

  LA ZONA DNS PRIVADA NO ES OPCIONAL, por la misma razón que la de PostgreSQL: sin ella el
  nombre resuelve a la dirección pública y el síntoma es un tiempo de espera agotado.
*/

@description('Región.')
param ubicacion string

@description('Prefijo de los nombres.')
param prefijo string

@description('Etiquetas comunes de la sección 12.2. Las arma `modules/comun/etiquetas.bicep`.')
param tags object

@description('Nombre del clúster. Se resuelve por DNS público y no puede repetirse en todo Azure.')
param nombreRedis string

@description('Identificador de la VNet, para enlazar la zona DNS privada.')
param vnetId string

@description('Subred donde aterriza el punto de conexión privado.')
param subredEndpointsId string

// El puerto de Managed Redis con TLS. No es configurable en el nivel Balanced.
var puertoTls = 10000

resource redis 'Microsoft.Cache/redisEnterprise@2024-10-01' = {
  name: nombreRedis
  location: ubicacion
  tags: tags
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
    port: puertoTls
    evictionPolicy: 'VolatileLRU'
    clusteringPolicy: 'EnterpriseCluster'
  }
}

resource zonaDnsRedis 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  // La zona de Managed Redis es distinta de la del servicio clásico.
  name: 'privatelink.redis.azure.net'
  location: 'global'
  tags: tags
}

resource enlaceDnsRedis 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: zonaDnsRedis
  name: 'enlace-vnet'
  location: 'global'
  tags: tags
  properties: {
    virtualNetwork: { id: vnetId }
    registrationEnabled: false
  }
}

resource endpointRedis 'Microsoft.Network/privateEndpoints@2023-09-01' = {
  name: '${prefijo}-pe-redis'
  location: ubicacion
  tags: tags
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

// La clave de acceso NO sale de aquí: una salida de despliegue queda en el historial del grupo
// de recursos. `datos.bicep` la lee directamente de la base con `listKeys`.
output nombre string = redis.name
output host string = redis.properties.hostName
output puertoTls int = puertoTls
