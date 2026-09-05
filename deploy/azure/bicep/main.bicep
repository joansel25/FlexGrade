/*
  Punto de entrada del despliegue de la infraestructura efímera.

  QUÉ ES «EFÍMERA» Y POR QUÉ

  Este proyecto es académico y vive de un crédito de estudiante. La arquitectura que pide
  `INFRASTRUCTURE.md` —Application Gateway con WAF, PostgreSQL con réplica, autoescalado— cuesta
  unos 250 USD al mes, pero **menos de 10 USD por una sesión de seis horas**. El problema nunca
  fue el recurso: fue dejarlo encendido.

  De ahí que la infraestructura sea código y no una lista de pasos en el portal. Destruirla y
  recrearla solo es razonable si es un comando; con cuarenta minutos de clics cada vez, nadie la
  destruye y el crédito se agota en tres semanas.

  DOS GRUPOS DE RECURSOS, Y LA SEPARACIÓN NO ES COSMÉTICA

    matricula-base   ACR y Key Vault. ~5 USD/mes. NUNCA se borra.
    matricula-demo   todo lo que declara este archivo. Se crea y se destruye.

  El Key Vault vive fuera porque tiene BORRADO LÓGICO de 90 días: si se destruyera con el resto,
  su nombre quedaría reservado y el segundo despliegue fallaría con «name already in use», sin
  decir en ningún momento que el recurso está en la papelera. Es el fallo que hace que un montaje
  funcione una vez y a la siguiente no.

  El ACR vive fuera porque guarda las imágenes: si se borrara, cada sesión empezaría
  reconstruyendo y volviendo a subir la imagen antes de que el App Service pudiera arrancar.

  CUÁNTO TARDA

  Unos cuarenta minutos, y no baja de ahí: Redis ronda los veinte y PostgreSQL con alta
  disponibilidad otros quince. Bicep los crea en paralelo, pero no puede acelerarlos. **No se
  lanza cinco minutos antes de sustentar.**
*/

targetScope = 'resourceGroup'

@description('Región. Debe tener zonas de disponibilidad: sin ellas la alta disponibilidad de PostgreSQL no se puede activar.')
param ubicacion string = resourceGroup().location

@description('Prefijo de todos los nombres.')
param prefijo string = 'matricula'

@description('Usuario administrador de PostgreSQL.')
param usuarioAdminPostgres string = 'matricula'

@description('Contraseña del administrador de PostgreSQL. Se pasa desde el Key Vault persistente; nunca se escribe en un archivo de parámetros.')
@secure()
param claveAdminPostgres string

@description('Nivel de PostgreSQL. `GeneralPurpose` es el que admite la réplica que pide el documento; `Burstable` es más barato y NO la admite.')
@allowed(['Burstable', 'GeneralPurpose'])
param nivelPostgres string = 'GeneralPurpose'

@description('SKU de PostgreSQL. Tiene que corresponder con el nivel: `Standard_B1ms` para Burstable, `Standard_D2ds_v4` para GeneralPurpose.')
param skuPostgres string = 'Standard_D2ds_v4'

// La alta disponibilidad se deduce del nivel en vez de recibirse aparte. Con `Burstable` y
// `altaDisponibilidad: true` el despliegue falla a los quince minutos, después de haber creado
// media infraestructura: es la clase de contradicción que conviene hacer imposible de expresar.
var altaDisponibilidad = nivelPostgres != 'Burstable'

// Los nombres de PostgreSQL y Redis se resuelven por DNS público y tienen que ser únicos en
// todo Azure. `uniqueString` da un sufijo estable para un mismo grupo de recursos: el mismo
// despliegue repetido devuelve los mismos nombres, y no se crean recursos duplicados.
var sufijo = take(uniqueString(resourceGroup().id), 6)

module red 'modules/red.bicep' = {
  name: 'red'
  params: {
    ubicacion: ubicacion
    prefijo: prefijo
  }
}

module datos 'modules/datos.bicep' = {
  name: 'datos'
  params: {
    ubicacion: ubicacion
    prefijo: prefijo
    sufijo: sufijo
    vnetId: red.outputs.vnetId
    subredDatosId: red.outputs.subredDatosId
    subredEndpointsId: red.outputs.subredEndpointsId
    usuarioAdmin: usuarioAdminPostgres
    claveAdmin: claveAdminPostgres
    skuPostgres: skuPostgres
    nivelPostgres: nivelPostgres
    altaDisponibilidad: altaDisponibilidad
  }
}

// ---------------------------------------------------------------------------
// Salidas: lo que hace falta para componer la configuración de la aplicación
// ---------------------------------------------------------------------------
//
// Ninguna lleva credenciales dentro. Las salidas de un despliegue quedan en el historial del
// grupo de recursos y las lee cualquiera con permiso de lectura.

output vnetNombre string = red.outputs.vnetNombre
output subredAppId string = red.outputs.subredAppId
output subredGatewayId string = red.outputs.subredGatewayId
output ipDeSalida string = red.outputs.ipSalidaDireccion

output postgresHost string = datos.outputs.postgresHost
output baseDeDatos string = datos.outputs.baseDeDatosNombre
output redisHost string = datos.outputs.redisHost
output redisPuerto int = datos.outputs.redisPuertoTls

// Recordatorio de cómo se arman las dos cadenas que la aplicación necesita, sin armarlas aquí.
output plantillaDatabaseUrl string = 'postgresql+psycopg://${usuarioAdminPostgres}:<clave>@${datos.outputs.postgresHost}:5432/${datos.outputs.baseDeDatosNombre}?sslmode=require'
output plantillaRedisUrl string = 'rediss://:<clave>@${datos.outputs.redisHost}:${datos.outputs.redisPuertoTls}/0'
