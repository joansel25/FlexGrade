// Alerta 5 de la sección 11.1: cambios de permisos o de políticas. Grupo persistente.
//
// Lee el Registro de actividad, no el workspace: dispara por evento, en cuanto alguien crea o
// borra una asignación de rol o de política en cualquier punto de la suscripción. Es la alerta
// que avisa de que la gobernanza se ha tocado, así que no puede depender de que la exportación
// del registro al workspace esté funcionando.

@description('Prefijo de los nombres.')
param prefijo string

@description('Etiquetas comunes de la sección 12.2.')
param tags object

@description('Identificador del grupo de acciones.')
param grupoAccionesId string

resource cambiosDePermisos 'Microsoft.Insights/activityLogAlerts@2020-10-01' = {
  name: '${prefijo}-alerta-cambios-permisos-politicas'
  // Las alertas del registro de actividad son globales.
  location: 'global'
  tags: tags
  properties: {
    description: 'Alerta 5 (11.1): alta o baja de una asignación de rol o de política.'
    enabled: true
    // TODA la suscripción: está dedicada a FlexGrade. Si dejara de estarlo, se limitaría a los
    // identificadores de los grupos del proyecto.
    scopes: [subscription().id]
    condition: {
      allOf: [
        {
          field: 'category'
          equals: 'Administrative'
        }
        {
          anyOf: [
            {
              field: 'operationName'
              equals: 'Microsoft.Authorization/roleAssignments/write'
            }
            {
              field: 'operationName'
              equals: 'Microsoft.Authorization/roleAssignments/delete'
            }
            {
              field: 'operationName'
              equals: 'Microsoft.Authorization/policyAssignments/write'
            }
            {
              field: 'operationName'
              equals: 'Microsoft.Authorization/policyAssignments/delete'
            }
          ]
        }
      ]
    }
    actions: {
      actionGroups: [
        {
          actionGroupId: grupoAccionesId
        }
      ]
    }
  }
}

output id string = cambiosDePermisos.id
