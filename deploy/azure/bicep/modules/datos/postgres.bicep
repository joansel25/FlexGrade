/*
  PostgreSQL Flexible Server, inyectado en la VNet.

  LA ZONA DNS PRIVADA NO ES OPCIONAL. Sin ella, el nombre del servidor resuelve a su dirección
  PÚBLICA, que está deshabilitada, y el error que se ve es un tiempo de espera agotado que no
  menciona el DNS por ningún lado. Con ella, el mismo nombre resuelve a la dirección privada.
*/

@description('Región.')
param ubicacion string

@description('Prefijo de los nombres. También nombra la zona DNS privada.')
param prefijo string

@description('Etiquetas comunes de la sección 12.2. Las arma `modules/comun/etiquetas.bicep`.')
param tags object

@description('Nombre del servidor. Se resuelve por DNS público y no puede repetirse en todo Azure.')
param nombreServidor string

@description('Identificador de la VNet, para enlazar la zona DNS privada.')
param vnetId string

@description('Subred delegada donde se inyecta el servidor.')
param subredDatosId string

@description('Usuario administrador.')
param usuarioAdmin string

@description('Contraseña del administrador. Llega del Key Vault persistente, nunca escrita en un archivo de parámetros.')
@secure()
param claveAdmin string

@description('SKU. La alta disponibilidad NO existe en el nivel Burstable (B1ms): exige General Purpose o superior.')
param skuPostgres string = 'Standard_D2ds_v4'

@description('Nivel del SKU. `Burstable` es el barato y no admite standby; `GeneralPurpose` es el que el documento pide.')
@allowed(['Burstable', 'GeneralPurpose', 'MemoryOptimized'])
param nivelPostgres string = 'GeneralPurpose'

@description('Alta disponibilidad con réplica en otra zona. Solo se puede activar si el nivel es GeneralPurpose o superior.')
param altaDisponibilidad bool = true

@description('Si se crea la alerta de almacenamiento (alerta 4 de 11.1).')
param desplegarAlertas bool = false

@description('Grupo de acciones al que avisa la alerta. Vive en el grupo persistente.')
param grupoAccionesId string = ''

// El nombre de la zona para el acceso privado de Flexible Server TIENE que terminar en
// `.private.postgres.database.azure.com`. Con cualquier otro sufijo, Azure rechaza el
// despliegue del servidor.
resource zonaDnsPostgres 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: '${prefijo}.private.postgres.database.azure.com'
  location: 'global'
  tags: tags
}

resource enlaceDnsPostgres 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: zonaDnsPostgres
  name: 'enlace-vnet'
  location: 'global'
  tags: tags
  properties: {
    virtualNetwork: { id: vnetId }
    // Sin registro automático: las entradas de esta zona las crea el propio servidor.
    registrationEnabled: false
  }
}

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2022-12-01' = {
  name: nombreServidor
  location: ubicacion
  tags: tags
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
// Cifrado en tránsito: el tramo API -> PostgreSQL (5432) de la sección 10.2
// ---------------------------------------------------------------------------
//
// `require_secure_transport` ya viene en ON por defecto en Flexible Server. Se declara igual:
// un valor por defecto se puede cambiar desde el portal sin dejar rastro en el código, y uno
// declarado lo restaura el siguiente despliegue. La aplicación ya conecta con
// `sslmode=require` (lo compone `datos.bicep`), así que nada cambia para ella.
//
// LAS TRES CONFIGURACIONES VAN EN FILA, cada una esperando a la anterior. Flexible Server
// rechaza dos cambios de configuración simultáneos con `ServerIsBusy`, y ARM, sin un
// `dependsOn`, las lanzaría en paralelo: el despliegue fallaría de forma intermitente según
// cuál llegara primero.

resource transporteSeguro 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2022-12-01' = {
  parent: postgres
  name: 'require_secure_transport'
  properties: {
    value: 'ON'
    source: 'user-override'
  }
  dependsOn: [extensionesPermitidas]
}

resource versionMinimaTls 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2022-12-01' = {
  parent: postgres
  name: 'ssl_min_protocol_version'
  properties: {
    value: 'TLSv1.2'
    source: 'user-override'
  }
  dependsOn: [transporteSeguro]
}

// ---------------------------------------------------------------------------
// Alerta 4 de 11.1: capacidad de almacenamiento
// ---------------------------------------------------------------------------
//
// Es la única alerta que vive en el grupo EFÍMERO, junto al servidor: una alerta de métricas
// apunta al recurso, y el recurso nace y muere con cada sesión. Las otras cinco leen el
// workspace persistente y viven allí.
//
// 32 GB es el mínimo que se aprovisiona (ver arriba) y el almacenamiento solo se puede ampliar,
// nunca reducir: el aviso al 80 % da margen para decidir antes de que el servidor pase a solo
// lectura al llenarse.

resource alertaAlmacenamiento 'Microsoft.Insights/metricAlerts@2018-03-01' = if (desplegarAlertas) {
  name: '${prefijo}-alerta-almacenamiento-postgres'
  location: 'global'
  tags: tags
  properties: {
    description: 'Alerta 4 (11.1): el almacenamiento de PostgreSQL supera el 80 %.'
    severity: 2
    enabled: true
    scopes: [postgres.id]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          criterionType: 'StaticThresholdCriterion'
          name: 'almacenamiento-sobre-80'
          metricNamespace: 'Microsoft.DBforPostgreSQL/flexibleServers'
          metricName: 'storage_percent'
          operator: 'GreaterThan'
          threshold: 80
          timeAggregation: 'Average'
        }
      ]
    }
    actions: [
      {
        actionGroupId: grupoAccionesId
      }
    ]
  }
}

output nombre string = postgres.name
output host string = postgres.properties.fullyQualifiedDomainName
output baseDeDatosNombre string = baseDeDatos.name
