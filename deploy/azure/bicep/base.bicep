/*
  El grupo PERSISTENTE: registro de imágenes, almacén de secretos, observabilidad y alertas.

  Cuesta unos 5 USD al mes más lo que consuman las alertas de logs, y es el precio de que destruir
  y recrear el resto sea fiable.

  POR QUÉ ESTOS RECURSOS VIVEN FUERA DEL GRUPO EFÍMERO

  **El Key Vault tiene borrado lógico de 90 días y no se puede desactivar.** Si se destruyera con
  el resto, su nombre quedaría reservado y el SEGUNDO despliegue fallaría con «name already in
  use», sin mencionar en ningún momento que el recurso está en la papelera. Es exactamente el
  fallo que hace que un montaje funcione una vez y a la siguiente no, y que cuesta media hora
  entender la primera vez que se ve.

  **El ACR guarda las imágenes.** Si se borrara, cada sesión de pruebas empezaría reconstruyendo
  y volviendo a subir la imagen antes de que el App Service pudiera arrancar siquiera.

  **La observabilidad se acumula** mientras la infraestructura va y viene: el workspace,
  Application Insights, el grupo de acciones y las alertas que leen el workspace (11.1).

  Se despliega con `scripts/desplegar-base.sh`, ANTES que la demo: `main.bicep` lee de aquí el
  componente de Application Insights y el grupo de acciones.

  REDESPLEGARLO YA NO ES PELIGROSO. Con las políticas de acceso del Key Vault declaradas como
  lista, redesplegar este archivo borraba el permiso que `permisos.bicep` había dado a la
  aplicación. Con RBAC cada permiso es un recurso aparte y el almacén no los toca.
*/

targetScope = 'resourceGroup'

import { etiquetas } from 'modules/comun/etiquetas.bicep'
import { sufijo, idGrupo, nombresBase, nombresEfimeros } from 'modules/comun/nombres.bicep'
import { roles, gruposEntra } from 'modules/comun/roles.bicep'

// La única región verificada (13.2): Estados Unidos figura entre los países con nivel adecuado de
// protección de la Circular Externa 005 de 2017 de la SIC. Añadir otra solo si su país está en esa
// lista.
@description('Región. La misma que el grupo efímero, para que el App Service no cruce regiones al descargar la imagen.')
@allowed(['centralus'])
param ubicacion string = 'centralus'

@description('Prefijo de los nombres.')
param prefijo string = 'matricula'

@description('Equipo dueño, para la etiqueta `Dueno`. Un identificador de equipo, nunca el nombre de una persona (12.2). Sin valor por defecto (14).')
@minLength(1)
param dueno string

@description('Código académico de centro de costo, para la etiqueta `CentroCosto`. Sin valor por defecto (14).')
@minLength(1)
param centroCosto string

@description('''
  Protección contra purga del Key Vault. ES IRREVERSIBLE: una vez activada no se puede desactivar,
  y un almacén borrado no se podrá eliminar del todo hasta que pasen sus 90 días de retención.
  Se recomienda activarla porque el almacén es persistente y guarda el historial del secreto JWT.
''')
param protegerPurgaKeyVault bool

@description('Correos del grupo de acciones (11.2). Sin valor por defecto (14).')
@minLength(1)
param correosAlertas string[]

@description('Grupos de Entra de los perfiles de 10.1. Vacío = sin asignar.')
param grupos gruposEntra

@description('Nombre del grupo EFÍMERO, para calcular los identificadores de lo que vigilan las alertas.')
param grupoEfimero string = 'matricula-demo'

@description('Retención general del workspace, en días (11.2). Pendiente de validar en coste (14).')
@minValue(30)
@maxValue(730)
param retencionGeneralDias int = 30

@description('Retención de las tablas de auditoría, en días (11.2). Pendiente de validar en coste (14).')
@minValue(30)
@maxValue(730)
param retencionAuditoriaDias int = 90

// Sin `Vigencia`: este grupo no caduca.
var tags = etiquetas('compartido', dueno, centroCosto, '')

var nombres = nombresBase(prefijo, sufijo(resourceGroup().id))

// Lo que vigilan las alertas, calculado con la misma función con que `main.bicep` lo crea.
var nombresDemo = nombresEfimeros(prefijo, sufijo(idGrupo(subscription().id, grupoEfimero)))
var idPlan = resourceId(grupoEfimero, 'Microsoft.Web/serverfarms', nombresDemo.plan)
var idApp = resourceId(grupoEfimero, 'Microsoft.Web/sites', nombresDemo.app)
var idGateway = resourceId(grupoEfimero, 'Microsoft.Network/applicationGateways', nombresDemo.gateway)

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: nombres.acr
  location: ubicacion
  tags: tags
  sku: {
    // Basic: 10 GB y sin replicación geográfica. La imagen del backend ronda los 200 MB.
    name: 'Basic'
  }
  properties: {
    // El usuario administrador se queda APAGADO. La descarga la hace el App Service con su
    // identidad administrada y el rol `AcrPull`: así no hay ninguna contraseña de registro
    // guardada en la configuración de la aplicación, donde la leería cualquiera con permiso de
    // lectura sobre el recurso.
    adminUserEnabled: false
  }
}

// ---------------------------------------------------------------------------
// El Key Vault (10.1, 10.3)
// ---------------------------------------------------------------------------

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: nombres.keyVault
  location: ubicacion
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    // RBAC, SIN POLÍTICAS DE ACCESO (10.1). La versión anterior usaba políticas porque asignar
    // roles exige ser Owner o User Access Administrator; la cuenta del proyecto es Owner de la
    // suscripción, comprobado, así que esa razón ya no aplica.
    //
    // CONSECUENCIA QUE HAY QUE SABER: con RBAC, ser Owner NO da acceso a los datos. Para escribir
    // `jwt-secret` a mano hace falta asignarse TEMPORALMENTE «Key Vault Secrets Officer» y
    // retirarlo después. No va en Bicep a propósito (10.1): es un permiso de escritura sobre
    // secretos que no debe quedar asignado. El procedimiento está en el RUNBOOK.
    //
    // Lo que NO necesita ese rol: los secretos que escribe `datos/secretos.bicep` y la lectura de
    // `getSecret` en `main.bicep` son operaciones del PLANO DE CONTROL, y Owner las tiene.
    enableRbacAuthorization: true
    // Permite que un archivo de parámetros REFERENCIE un secreto de este almacén en vez de
    // llevar el valor dentro. Es lo que hace que la contraseña de PostgreSQL no pase nunca por
    // la línea de comandos ni por el archivo de parámetros, que está versionado.
    enabledForTemplateDeployment: true
    // 90 días es el mínimo y no se puede bajar. Está aquí para que quede claro por qué el
    // almacén no puede vivir en el grupo efímero.
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    // `null` y no `false`: Azure rechaza `false` explícito en esta propiedad.
    enablePurgeProtection: protegerPurgaKeyVault ? true : null
    publicNetworkAccess: 'Enabled'
  }
}

// «Habilitar registros de acceso a Key Vault» (10.3): quién leyó qué secreto y cuándo.
// `audit` es el grupo de categorías de auditoría; `AllMetrics` añade la disponibilidad y la
// latencia del almacén. Va al workspace de este mismo grupo.
resource diagnosticoKeyVault 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'a-log-analytics'
  scope: keyVault
  properties: {
    workspaceId: registros.id
    logs: [
      {
        categoryGroup: 'audit'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

// ---------------------------------------------------------------------------
// Dónde se guardan los registros
// ---------------------------------------------------------------------------
//
// POR QUÉ VIVE AQUÍ Y NO EN EL GRUPO EFÍMERO
//
// Si el área de trabajo se destruyera con el resto, cada sesión empezaría sin historia: los
// registros de la demostración del martes no existirían el miércoles, y lo único que se podría
// enseñar sería lo que acabara de pasar. Poniéndola en el grupo persistente, la infraestructura
// sigue siendo efímera pero la observabilidad se acumula.
//
// NO CUESTA NADA MIENTRAS NO SE USE. Log Analytics se factura por gigabyte ingerido, no por
// tener el recurso creado: un área de trabajo parada vale 0. Los primeros 5 GB al mes son
// gratuitos, y una sesión de sustentación genera unos pocos megabytes.
//
// QUÉ RECOGE, Y POR QUÉ IMPORTA QUE SEA ASÍ
//
// La aplicación escribe sus registros en JSON a la salida estándar —ver
// `app/infrastructure/logging/setup.py`—, con un identificador único por petición que también
// viaja en la cabecera `X-Request-ID` de la respuesta. Eso es lo que permite pasar de «me falló
// la inscripción esta mañana» a la línea exacta, entre millones, sin buscar por hora aproximada.

resource registros 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: nombres.registros
  location: ubicacion
  tags: tags
  properties: {
    sku: {
      // `PerGB2018` es el nivel vigente. El antiguo `Free` está retirado para áreas nuevas.
      name: 'PerGB2018'
    }
    // La retención GENERAL (11.2). Las tablas de auditoría guardan más: `monitoreo/telemetria.bicep`.
    retentionInDays: retencionGeneralDias
    workspaceCapping: {
      // Tope duro de ingesta diaria. No es paranoia: un bucle de errores puede generar
      // muchísimo registro en minutos, y este es el único recurso del proyecto cuyo coste
      // depende de lo que haga la aplicación en vez de del tiempo que esté encendida.
      //
      // OJO: si se alcanza, la recogida se corta hasta el día siguiente y las alertas que leen
      // el workspace (1, 2, 3 y 6) quedan CIEGAS sin avisar.
      dailyQuotaGb: 1
    }
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// ---------------------------------------------------------------------------
// Observabilidad y alertas (11.1, 11.2)
// ---------------------------------------------------------------------------

module telemetria 'modules/monitoreo/telemetria.bicep' = {
  name: 'telemetria'
  params: {
    ubicacion: ubicacion
    tags: tags
    nombreAppInsights: nombres.appInsights
    nombreRegistros: registros.name
    retencionAuditoriaDias: retencionAuditoriaDias
  }
}

module grupoAcciones 'modules/monitoreo/grupo-acciones.bicep' = {
  name: 'grupo-acciones'
  params: {
    tags: tags
    nombre: nombres.grupoAcciones
    correos: correosAlertas
  }
}

module alertasDeRegistros 'modules/monitoreo/alertas-registros.bicep' = {
  name: 'alertas-registros'
  params: {
    ubicacion: ubicacion
    prefijo: prefijo
    tags: tags
    registrosId: registros.id
    grupoAccionesId: grupoAcciones.outputs.id
    idPlan: idPlan
    idApp: idApp
    idGateway: idGateway
  }
}

module alertaDeActividad 'modules/monitoreo/alerta-actividad.bicep' = {
  name: 'alerta-actividad'
  params: {
    prefijo: prefijo
    tags: tags
    grupoAccionesId: grupoAcciones.outputs.id
  }
}

// ---------------------------------------------------------------------------
// Perfiles humanos (10.1)
// ---------------------------------------------------------------------------

module perfiles 'modules/acceso/perfiles-grupo.bicep' = {
  name: 'perfiles-grupo'
  params: {
    grupos: grupos
  }
}

// El operador de monitoreo lee el workspace. Es el único perfil con ámbito sobre un recurso de
// este grupo.
resource lectorDeRegistros 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(grupos.monitoreo)) {
  scope: registros
  name: guid(registros.id, grupos.monitoreo, roles.logAnalyticsReader)
  properties: {
    principalId: grupos.monitoreo
    principalType: 'Group'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.logAnalyticsReader)
  }
}

output acrNombre string = acr.name
output acrLoginServer string = acr.properties.loginServer
output keyVaultNombre string = keyVault.name
output keyVaultUri string = keyVault.properties.vaultUri
output registrosId string = registros.id
output registrosNombre string = registros.name
output appInsightsId string = telemetria.outputs.appInsightsId
output grupoAccionesId string = grupoAcciones.outputs.id

// Recordatorio del único secreto que NO escribe Bicep. Ver el RUNBOOK.
output recordatorio string = 'Falta crear a mano el secreto `jwt-secret` en ${keyVault.name}, con «Key Vault Secrets Officer» asignado temporalmente. Ver RUNBOOK.'
