/*
  Lo que se despliega sobre la SUSCRIPCIÓN y no sobre un grupo (sección 14, ámbitos de 1.4):

    - las etiquetas del grupo persistente (12.2: las del grupo no se heredan solas)
    - la exportación del Registro de actividad al workspace (11.1, 11.3)
    - el presupuesto mensual con sus tres avisos (12.3)
    - la iniciativa de Azure Policy y su asignación (13.3)
    - el rol de FinOps sobre el ámbito del presupuesto (10.1)

  VA DESPUÉS DE `base.bicep`, porque lee de allí el workspace y el grupo de acciones. Lo
  encadena `scripts/desplegar-base.sh`. El grupo EFÍMERO no se declara aquí: lo crea
  `scripts/levantar.sh` con sus etiquetas, en cada sesión.
*/

targetScope = 'subscription'

import { etiquetas } from 'modules/comun/etiquetas.bicep'
import { sufijo, idGrupo, nombresBase } from 'modules/comun/nombres.bicep'
import { roles } from 'modules/comun/roles.bicep'

@description('Región del despliegue y del grupo persistente (13.2).')
@allowed(['centralus'])
param ubicacion string = 'centralus'

@description('Prefijo de los nombres.')
param prefijo string = 'matricula'

@description('Grupo de recursos PERSISTENTE.')
param grupoBase string = 'matricula-base'

@description('Equipo dueño, para la etiqueta `Dueno` (12.2). Sin valor por defecto (14).')
@minLength(1)
param dueno string

@description('Código académico de centro de costo (12.2). Sin valor por defecto (14).')
@minLength(1)
param centroCosto string

@description('Monto mensual del presupuesto (12.3). Sin valor por defecto: lo fija FinOps (14).')
@minValue(1)
param montoPresupuesto int

@description('Primer día del mes en que empieza el presupuesto, AAAA-MM-01 (12.3).')
param inicioPresupuesto string

@description('Correos de los avisos del presupuesto (12.3). Sin valor por defecto (14).')
@minLength(1)
param correosPresupuesto string[]

@description('Identificador del grupo de Entra de FinOps (10.1). Vacío = sin asignar.')
param grupoFinops string

@description('`audit` evalúa la gobernanza sin rechazar nada; `enforce` bloquea (13.3).')
@allowed(['audit', 'enforce'])
param modoPoliticas string = 'audit'

@description('Grupos fuera de la gobernanza. `NetworkWatcherRG` lo crea Azure sin etiquetas.')
param gruposExcluidosDePoliticas string[] = ['NetworkWatcherRG']

var nombres = nombresBase(prefijo, sufijo(idGrupo(subscription().id, grupoBase)))
var registrosId = resourceId(subscription().subscriptionId, grupoBase, 'Microsoft.OperationalInsights/workspaces', nombres.registros)
var grupoAccionesId = resourceId(subscription().subscriptionId, grupoBase, 'Microsoft.Insights/actionGroups', nombres.grupoAcciones)

// Redeclarar el grupo persistente solo le pone las etiquetas: un grupo que ya existe en la misma
// región se actualiza, no se recrea, y su contenido no se toca.
resource grupoPersistente 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: grupoBase
  location: ubicacion
  tags: etiquetas('compartido', dueno, centroCosto, '')
}

module registroDeActividad 'modules/monitoreo/registro-actividad.bicep' = {
  name: 'registro-actividad'
  params: {
    registrosId: registrosId
  }
}

module presupuesto 'modules/costos/presupuesto.bicep' = {
  name: 'presupuesto'
  params: {
    monto: montoPresupuesto
    inicio: inicioPresupuesto
    correos: correosPresupuesto
    grupoAccionesId: grupoAccionesId
  }
}

module iniciativa 'modules/gobernanza/iniciativa.bicep' = {
  name: 'iniciativa-gobernanza'
}

module asignacion 'modules/gobernanza/asignacion.bicep' = {
  name: 'asignacion-gobernanza'
  params: {
    modo: modoPoliticas
    iniciativaId: iniciativa.outputs.iniciativaId
    gruposExcluidos: gruposExcluidosDePoliticas
  }
}

// FinOps sobre el ámbito del presupuesto, que es la suscripción (10.1, 12.3).
resource finops 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(grupoFinops)) {
  name: guid(subscription().id, grupoFinops, roles.costManagementContributor)
  properties: {
    principalId: grupoFinops
    principalType: 'Group'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.costManagementContributor)
  }
}

output asignacionPoliticas string = asignacion.outputs.id
output modoPoliticas string = modoPoliticas
