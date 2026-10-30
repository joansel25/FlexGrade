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

import { etiquetas } from 'modules/comun/etiquetas.bicep'
import { sufijo as calcularSufijo, idGrupo, nombresBase } from 'modules/comun/nombres.bicep'
import { gruposEntra } from 'modules/comun/roles.bicep'

// La única región verificada (13.2): Estados Unidos figura entre los países con nivel adecuado de
// protección de la Circular Externa 005 de 2017 de la SIC. Añadir otra solo si su país está en esa
// lista. Además tiene zonas de disponibilidad, sin las que la réplica de PostgreSQL no se activa.
@description('Región. Debe tener zonas de disponibilidad: sin ellas la alta disponibilidad de PostgreSQL no se puede activar.')
@allowed(['centralus'])
param ubicacion string = 'centralus'

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

@description('Grupo de recursos PERSISTENTE, donde viven el ACR y el Key Vault. Nunca se destruye.')
param grupoBase string = 'matricula-base'

@description('Nombre del Key Vault persistente. Sale de la salida `keyVaultNombre` de base.bicep.')
param nombreKeyVault string

@description('Nombre del ACR persistente. Sale de la salida `acrNombre` de base.bicep.')
param nombreAcr string

@description('Servidor de inicio de sesión del ACR. Sale de la salida `acrLoginServer` de base.bicep.')
param acrLoginServer string

@description('SKU del App Service. `B1` no admite autoescalado; `S1` es el que exige la sección 5 del documento.')
@allowed(['B1', 'S1'])
param skuAppService string = 'S1'

@description('Instancias con las que arranca la aplicación.')
@minValue(1)
param instanciasIniciales int = 1

@description('Etiqueta de la imagen a ejecutar. El pipeline la sustituye por `dev-<sha>`.')
param etiquetaImagen string = 'latest'

@description('Orígenes autorizados por CORS. Lo rellena el script de arranque con la URL del sitio estático, que no se conoce hasta que la cuenta de almacenamiento existe.')
param origenesCors string = ''

@description('Ambiente de la APLICACIÓN: se reporta en /health y decide el formato de los logs. NO es la etiqueta `Ambiente`: con `dev` el backend escribe texto plano y Log Analytics deja de poder leerlo.')
param ambiente string = 'demo'

@description('Valor de la etiqueta `Ambiente` (12.2): `dev` en el perfil económico, `demo` en el de demostración.')
@allowed(['dev', 'demo'])
param etiquetaAmbiente string

@description('Equipo dueño, para la etiqueta `Dueno` (12.2). Sin valor por defecto (14).')
@minLength(1)
param dueno string

@description('Código académico de centro de costo (12.2). Sin valor por defecto (14).')
@minLength(1)
param centroCosto string

@description('Fecha de revisión de la etiqueta `Vigencia`, AAAA-MM-DD (12.2). La pone `levantar.sh`: el día siguiente, porque esto es una sesión.')
param vigencia string = ''

@description('Grupos de Entra de los perfiles de 10.1. Vacío = sin asignar.')
param grupos gruposEntra

@description('Si se crea la alerta de almacenamiento de PostgreSQL (alerta 4 de 11.1). Va en el perfil de demostración.')
param desplegarAlertas bool = false

@description('Si se ejecutan las migraciones y el seed tras desplegar. Es lo único que puede escribir el esquema: PostgreSQL está en red privada y no lo alcanza nada de fuera.')
param ejecutarMigraciones bool = true

@description('Si las migraciones además siembran datos de ejemplo. En un ambiente real va en false.')
param sembrarDatos bool = true

@description('Si se crea la regla de autoescalado. Requiere `skuAppService: S1`: el nivel Basic la acepta y NUNCA dispara, que es peor que no tenerla.')
param desplegarAutoescalado bool = false

@description('Pone el autoescalado en las capacidades del PICO desde el arranque, sin esperar al horario. Es para sustentar, y son 0,57 USD/hora solo de App Service.')
param autoescaladoEnModoDemostracion bool = false

@description('Si se despliega Application Gateway con WAF. ES LA LÍNEA MÁS CARA: ~0,46 USD/hora, casi cuatro veces el resto del perfil económico junto.')
param desplegarBorde bool = false

@description('Si se despliega el NAT Gateway. Es el 37% de la factura del perfil económico —0,045 USD/hora— y App Service ya da direcciones de salida estables por su cuenta. Lo pide la sección 3 del documento, así que va encendido para sustentar y apagado para probar.')
param desplegarNat bool = true

@description('Identificador del área de trabajo de Log Analytics, que vive en el grupo PERSISTENTE. Sale de la salida `registrosId` de base.bicep. Vacío desactiva la recogida de registros.')
param registrosId string = ''

// La alta disponibilidad se deduce del nivel en vez de recibirse aparte. Con `Burstable` y
// `altaDisponibilidad: true` el despliegue falla a los quince minutos, después de haber creado
// media infraestructura: es la clase de contradicción que conviene hacer imposible de expresar.
var altaDisponibilidad = nivelPostgres != 'Burstable'

// Los nombres de PostgreSQL y Redis se resuelven por DNS público y tienen que ser únicos en
// todo Azure. `uniqueString` da un sufijo estable para un mismo grupo de recursos: el mismo
// despliegue repetido devuelve los mismos nombres, y no se crean recursos duplicados.
var sufijo = calcularSufijo(resourceGroup().id)

var tags = etiquetas(etiquetaAmbiente, dueno, centroCosto, vigencia)

// Lo que vive en el grupo persistente y se lee desde aquí. Se calcula con la misma función con la
// que `base.bicep` lo nombra: no hace falta pasarlo por los archivos de parámetros.
var nombresPersistentes = nombresBase(prefijo, calcularSufijo(idGrupo(subscription().id, grupoBase)))
var grupoAccionesId = resourceId(grupoBase, 'Microsoft.Insights/actionGroups', nombresPersistentes.grupoAcciones)

resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: nombresPersistentes.appInsights
  scope: resourceGroup(grupoBase)
}

module red 'modules/red/red.bicep' = {
  name: 'red'
  params: {
    ubicacion: ubicacion
    prefijo: prefijo
    tags: tags
    desplegarNat: desplegarNat
  }
}

module datos 'modules/datos/datos.bicep' = {
  name: 'datos'
  params: {
    ubicacion: ubicacion
    prefijo: prefijo
    tags: tags
    sufijo: sufijo
    vnetId: red.outputs.vnetId
    subredDatosId: red.outputs.subredDatosId
    subredEndpointsId: red.outputs.subredEndpointsId
    usuarioAdmin: usuarioAdminPostgres
    claveAdmin: claveAdminPostgres
    skuPostgres: skuPostgres
    nivelPostgres: nivelPostgres
    altaDisponibilidad: altaDisponibilidad
    grupoBase: grupoBase
    nombreKeyVault: nombreKeyVault
    desplegarAlertas: desplegarAlertas
    grupoAccionesId: desplegarAlertas ? grupoAccionesId : ''
  }
}

// ---------------------------------------------------------------------------
// La aplicación, y el orden que hay que respetar
// ---------------------------------------------------------------------------
//
// La identidad administrada no existe hasta que la aplicación se crea, y los permisos no se
// pueden conceder antes que la identidad. Pero la configuración con las referencias al Key
// Vault no se puede aplicar antes que los permisos, o quedan sin resolver y la aplicación
// arranca con la cadena literal `@Microsoft.KeyVault(...)` como valor de `DATABASE_URL`.
//
// La cadena queda LINEAL: aplicación -> permisos -> ajustes. La primera versión intentaba
// meter los ajustes dentro de `app.bicep` y el compilador la rechazó por un ciclo que era real.

module app 'modules/aplicacion/app.bicep' = {
  name: 'app'
  params: {
    ubicacion: ubicacion
    prefijo: prefijo
    tags: tags
    sufijo: sufijo
    skuPlan: skuAppService
    instancias: instanciasIniciales
    subredAppId: red.outputs.subredAppId
    acrLoginServer: acrLoginServer
    etiquetaImagen: etiquetaImagen
  }
}

module permisos 'modules/aplicacion/permisos.bicep' = {
  name: 'permisos'
  scope: resourceGroup(grupoBase)
  params: {
    nombreKeyVault: nombreKeyVault
    nombreAcr: nombreAcr
    principalId: app.outputs.principalId
    // El `!` afirma que no es nulo, y el ternario de delante es lo que lo garantiza: la
    // identidad solo se consulta cuando se creó.
    principalTareas: ejecutarMigraciones ? identidadTareas!.properties.principalId : ''
  }
}

// ---------------------------------------------------------------------------
// El esquema de la base de datos
// ---------------------------------------------------------------------------
//
// La identidad va PRIMERO y es asignada por el usuario, no del sistema. Con una del sistema, el
// permiso de descarga no podría concederse antes de que el contenedor existiera, y la descarga
// ocurre al arrancar: sería demasiado tarde.

resource identidadTareas 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' =
  if (ejecutarMigraciones) {
    name: '${prefijo}-id-tareas'
    location: ubicacion
    tags: tags
  }

resource almacen 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: nombreKeyVault
  scope: resourceGroup(grupoBase)
}

module migraciones 'modules/operacion/migraciones.bicep' = if (ejecutarMigraciones) {
  name: 'migraciones'
  params: {
    ubicacion: ubicacion
    prefijo: prefijo
    tags: tags
    subredTareasId: red.outputs.subredTareasId
    acrLoginServer: acrLoginServer
    etiquetaImagen: etiquetaImagen
    identidadId: identidadTareas!.id
    // Se lee del Key Vault en el momento del despliegue. No pasa por un archivo de parámetros
    // ni por la línea de comandos.
    databaseUrl: almacen.getSecret('database-url')
    sembrarDatos: sembrarDatos
  }
  // El esquema no se puede escribir antes de que exista el servidor, y el permiso de descarga
  // tiene que estar concedido antes de que el contenedor intente bajar la imagen.
  dependsOn: [datos, permisos]
}

module ajustes 'modules/aplicacion/ajustes.bicep' = {
  name: 'ajustes'
  params: {
    nombreApp: app.outputs.nombreApp
    referenciaBaseDeDatos: datos.outputs.uriSecretoBaseDeDatos
    referenciaRedis: datos.outputs.uriSecretoRedis
    referenciaJwt: datos.outputs.uriSecretoJwt
    ambiente: ambiente
    origenesCors: origenesCors
    etiquetaImagen: etiquetaImagen
    conexionAppInsights: appInsights.properties.ConnectionString
  }
  // Explícito y no deducido: Bicep no puede saber que aplicar esta configuración ANTES de que
  // el permiso exista deja las referencias al Key Vault sin resolver.
  dependsOn: [permisos]
}

// ---------------------------------------------------------------------------
// Los registros
// ---------------------------------------------------------------------------
//
// El área de trabajo NO se crea aquí: vive en el grupo persistente, para que los registros
// sobrevivan a la destrucción. Esto solo conecta la salida de la aplicación —y la del
// cortafuegos, cuando existe— con ella.
//
// Aparece ANTES que el borde en el archivo aunque dependa de él. No es un descuido: Bicep
// ordena los módulos por sus dependencias reales, no por su posición en el texto, y agrupar
// aquí todo lo que tiene que ver con registros se lee mejor que perseguirlo por el archivo.

module observabilidad 'modules/operacion/observabilidad.bicep' = if (!empty(registrosId)) {
  name: 'observabilidad'
  params: {
    registrosId: registrosId
    nombreApp: app.outputs.nombreApp
    nombrePlan: app.outputs.planNombre
    nombrePostgres: datos.outputs.postgresNombre
    nombreGateway: desplegarBorde ? borde!.outputs.nombreGateway : ''
  }
}

// ---------------------------------------------------------------------------
// Perfiles humanos (10.1)
// ---------------------------------------------------------------------------
//
// Nacen y mueren con el grupo. Con los grupos de Entra vacíos —hoy, porque la cuenta del
// proyecto no puede crearlos— no se asigna nada.

module perfilesDelGrupo 'modules/acceso/perfiles-grupo.bicep' = {
  name: 'perfiles-grupo'
  params: {
    grupos: grupos
  }
}

module perfilesDeRecursos 'modules/acceso/perfiles-recursos.bicep' = {
  name: 'perfiles-recursos'
  params: {
    grupos: grupos
    nombreApp: app.outputs.nombreApp
    nombreCuentaFrontend: desplegarBorde ? borde!.outputs.cuentaAlmacenamientoWeb : ''
  }
}

// ---------------------------------------------------------------------------
// El autoescalado y el borde: la parte cara, y por eso opcional
// ---------------------------------------------------------------------------
//
// Los dos van apagados por defecto. El perfil económico —el que se usa para probar que el
// sistema funciona— no los enciende; el de demostración sí. La diferencia entre uno y otro es
// de 0,12 a más de 1,20 USD/hora, así que la elección conviene que sea explícita y no un
// descuido.
//
// EL AUTOESCALADO EXIGE S1 Y NO SE COMPRUEBA SOLO. Sobre un plan B1, Azure acepta la regla, la
// muestra en el portal y no la aplica nunca. La condición mira las dos cosas para que un perfil
// económico con el autoescalado encendido por error no cree una regla muerta que aparenta
// funcionar.

module escalado 'modules/operacion/escalado.bicep' = if (desplegarAutoescalado && skuAppService == 'S1') {
  name: 'escalado'
  params: {
    ubicacion: ubicacion
    prefijo: prefijo
    tags: tags
    planId: app.outputs.planId
    planNombre: app.outputs.planNombre
    modoDemostracion: autoescaladoEnModoDemostracion
  }
}

module borde 'modules/borde/borde.bicep' = if (desplegarBorde) {
  name: 'borde'
  params: {
    ubicacion: ubicacion
    prefijo: prefijo
    tags: tags
    sufijo: sufijo
    subredGatewayId: red.outputs.subredGatewayId
    hostApp: app.outputs.hostApp
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
// Vacía si el NAT está apagado; en ese caso la salida es el conjunto de direcciones del
// App Service: `az webapp show --query possibleOutboundIpAddresses`.
output ipDeSalida string = red.outputs.ipSalidaDireccion

output nombreApp string = app.outputs.nombreApp
output urlApp string = 'https://${app.outputs.hostApp}'
output urlSalud string = 'https://${app.outputs.hostApp}/health/ready'
output planNombre string = app.outputs.planNombre

output postgresHost string = datos.outputs.postgresHost
output baseDeDatos string = datos.outputs.baseDeDatosNombre
output redisHost string = datos.outputs.redisHost
output redisPuerto int = datos.outputs.redisPuertoTls

// Del borde y el autoescalado, solo si se pidieron. Sin la comprobación, ARM falla al intentar
// leer la salida de un módulo que no se desplegó.
output urlGateway string = desplegarBorde ? borde!.outputs.urlGateway : ''
output ipGateway string = desplegarBorde ? borde!.outputs.ipGateway : ''
output cuentaFrontend string = desplegarBorde ? borde!.outputs.cuentaAlmacenamientoWeb : ''
output urlFrontend string = desplegarBorde ? borde!.outputs.urlFrontend : ''
output reglaAutoescalado string = (desplegarAutoescalado && skuAppService == 'S1') ? escalado!.outputs.nombreRegla : ''

// Las cadenas de conexión NO se devuelven: las escribe `datos.bicep` directamente en el Key
// Vault persistente. Una salida de despliegue queda en el historial del grupo de recursos.
