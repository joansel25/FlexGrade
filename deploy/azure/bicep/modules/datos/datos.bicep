/*
  Datos: PostgreSQL y Redis en la red privada, y sus cadenas de conexión en el Key Vault.

  Este archivo solo COMPONE: cada servicio vive en su módulo (`postgres.bicep`, `redis.bicep`) y
  las cadenas se escriben con `secretos.bicep`. Lo que se queda aquí es lo único que necesita
  conocer las dos mitades a la vez.

  LO QUE MÁS TARDA DE TODO EL DESPLIEGUE. Redis ronda los veinte minutos y PostgreSQL con alta
  disponibilidad otros quince. Los dos módulos no dependen uno del otro, así que Bicep los crea
  EN PARALELO, lo que convierte treinta y cinco minutos en veinte. Hacer que uno dependa del
  otro —aunque fuera por un `dependsOn` de más— devolvería esos quince minutos.
*/

@description('Región donde se crea todo.')
param ubicacion string

@description('Prefijo de los nombres.')
param prefijo string

@description('Etiquetas comunes de la sección 12.2. Las arma `modules/comun/etiquetas.bicep`.')
param tags object

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

@description('Si se crea la alerta de almacenamiento de PostgreSQL (alerta 4 de 11.1). Va encendida en el perfil de demostración.')
param desplegarAlertas bool

@description('Identificador del grupo de acciones del grupo persistente. Vacío si no hay alertas.')
param grupoAccionesId string

import { nombresEfimeros } from '../comun/nombres.bicep'

// Los nombres se calculan AQUÍ y no dentro de cada módulo porque la clave de Redis se lee con un
// `existing` más abajo, y el nombre de un recurso `existing` tiene que conocerse al empezar el
// despliegue: no puede salir de la salida de otro módulo. Salen de `nombresEfimeros` porque las
// alertas del grupo persistente vigilan estos mismos recursos por su nombre.
var nombres = nombresEfimeros(prefijo, sufijo)

module postgres 'postgres.bicep' = {
  name: 'postgres'
  params: {
    ubicacion: ubicacion
    prefijo: prefijo
    tags: tags
    nombreServidor: nombres.postgres
    vnetId: vnetId
    subredDatosId: subredDatosId
    usuarioAdmin: usuarioAdmin
    claveAdmin: claveAdmin
    skuPostgres: skuPostgres
    nivelPostgres: nivelPostgres
    altaDisponibilidad: altaDisponibilidad
    desplegarAlertas: desplegarAlertas
    grupoAccionesId: grupoAccionesId
  }
}

module redis 'redis.bicep' = {
  name: 'redis'
  params: {
    ubicacion: ubicacion
    prefijo: prefijo
    tags: tags
    nombreRedis: nombres.redis
    vnetId: vnetId
    subredEndpointsId: subredEndpointsId
  }
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
// Azure la genera al crear la instancia y no se puede fijar de antemano. Por eso se lee con un
// `existing` y no como salida de `redis.bicep`, que la dejaría escrita en el historial.

resource baseRedis 'Microsoft.Cache/redisEnterprise/databases@2024-10-01' existing = {
  name: '${nombres.redis}/default'
}

module secretos 'secretos.bicep' = {
  name: 'secretos'
  scope: resourceGroup(grupoBase)
  params: {
    nombreKeyVault: nombreKeyVault
    databaseUrl: 'postgresql+psycopg://${usuarioAdmin}:${claveAdmin}@${postgres.outputs.host}:5432/${postgres.outputs.baseDeDatosNombre}?sslmode=require'
    // La clave la genera Azure al crear la base y se lee de ella, no del clúster. `/0` porque
    // `redis-py` espera un índice de base lógica.
    //
    // `listKeys` sobre un `existing` no crea dependencia por sí solo; la crea `redis.outputs`
    // en la misma cadena, que obliga a esperar al módulo ENTERO, base incluida. Si algún día la
    // cadena dejara de usar esas salidas, haría falta un `dependsOn: [redis]` explícito.
    redisUrl: 'rediss://:${baseRedis.listKeys().primaryKey}@${redis.outputs.host}:${redis.outputs.puertoTls}/0'
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

output postgresNombre string = postgres.outputs.nombre
output postgresHost string = postgres.outputs.host
output baseDeDatosNombre string = postgres.outputs.baseDeDatosNombre
output redisNombre string = redis.outputs.nombre
output redisHost string = redis.outputs.host
output redisPuertoTls int = redis.outputs.puertoTls

// Los identificadores de los secretos, SIN versión: el App Service resuelve siempre el último
// valor, así que tras recrear la infraestructura toma la cadena nueva sin tocar su
// configuración.
output uriSecretoBaseDeDatos string = secretos.outputs.uriBaseDeDatos
output uriSecretoRedis string = secretos.outputs.uriRedis
output uriSecretoJwt string = secretos.outputs.uriJwt
