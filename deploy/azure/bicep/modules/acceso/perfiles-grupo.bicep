// Los perfiles humanos de la sección 10.1 cuyo ámbito es un GRUPO DE RECURSOS. Se despliega
// sobre cada grupo del proyecto: desde `base.bicep` y desde `main.bicep`.
//
//   Infraestructura  Contributor
//   Seguridad        Resource Policy Contributor + RBAC Administrator CON CONDICIÓN
//   Monitoreo        Monitoring Contributor
//
// Un grupo de Entra vacío no recibe nada: ver `gruposEntra` en `comun/roles.bicep`.

targetScope = 'resourceGroup'

import { roles, gruposEntra } from '../comun/roles.bicep'

@description('Identificadores de los grupos de Entra. Vacío = sin asignar.')
param grupos gruposEntra

// LA CONDICIÓN DEL RBAC ADMINISTRATOR (10.1)
//
// Sin ella, quien tenga ese rol puede darse a sí mismo Owner: el rol sirve para delegar, y sin
// límite delega cualquier cosa. La condición restringe la creación Y el borrado de asignaciones a
// esta lista. Deja fuera a propósito Contributor, Owner y al propio RBAC Administrator: son
// justo los que permitirían escalar privilegios.
//
// Sintaxis de la delegación condicionada de Azure ABAC (`conditionVersion: '2.0'`): cada mitad
// dice «si la acción no es escribir/borrar una asignación, sin restricción; si lo es, solo con
// uno de estos roles». La de borrado mira `@Resource` porque la asignación ya existe.
var rolesDelegables = [
  roles.websiteContributor
  roles.storageBlobDataContributor
  roles.monitoringContributor
  roles.logAnalyticsReader
  roles.keyVaultSecretsUser
  roles.costManagementContributor
  roles.resourcePolicyContributor
]

var listaDelegables = join(rolesDelegables, ', ')

var condicionDelegacion = '((!(ActionMatches{\'Microsoft.Authorization/roleAssignments/write\'})) OR (@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {${listaDelegables}})) AND ((!(ActionMatches{\'Microsoft.Authorization/roleAssignments/delete\'})) OR (@Resource[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {${listaDelegables}}))'

var asignaciones = filter(
  [
    { principal: grupos.infraestructura, rol: roles.contributor, condicion: '' }
    { principal: grupos.seguridad, rol: roles.resourcePolicyContributor, condicion: '' }
    { principal: grupos.seguridad, rol: roles.rbacAdministrator, condicion: condicionDelegacion }
    { principal: grupos.monitoreo, rol: roles.monitoringContributor, condicion: '' }
  ],
  a => !empty(a.principal)
)

resource asignacion 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for a in asignaciones: {
    // Determinista: el mismo grupo, principal y rol dan siempre el mismo nombre, y repetir el
    // despliegue no duplica nada.
    name: guid(resourceGroup().id, a.principal, a.rol)
    properties: {
      principalId: a.principal
      principalType: 'Group'
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', a.rol)
      condition: empty(a.condicion) ? null : a.condicion
      conditionVersion: empty(a.condicion) ? null : '2.0'
    }
  }
]

output asignadas int = length(asignaciones)
