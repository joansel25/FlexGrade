// El perfil de desarrollo de la sección 10.1, con ámbito sobre RECURSOS concretos del grupo
// efímero. Nace y muere con ellos en cada sesión.
//
//   Website Contributor            sobre el App Service de la API
//   Storage Blob Data Contributor  sobre la cuenta del frontend, si existe
//
// POR QUÉ SOBRE LA CUENTA Y NO SOBRE EL CONTENEDOR `$web` QUE PIDE EL DOCUMENTO: ese contenedor
// no existe al desplegar. Lo crea `scripts/lib/frontend.sh` al activar el sitio estático, que es
// una operación del plano de datos y no de ARM. Como es el ÚNICO contenedor de la cuenta, el
// alcance efectivo es el mismo.

targetScope = 'resourceGroup'

import { roles, gruposEntra } from '../comun/roles.bicep'

@description('Identificadores de los grupos de Entra. Vacío = sin asignar.')
param grupos gruposEntra

@description('Nombre del App Service de la API.')
param nombreApp string

@description('Nombre de la cuenta de almacenamiento del frontend. Vacío si el perfil no la crea.')
param nombreCuentaFrontend string = ''

var hayDesarrollo = !empty(grupos.desarrollo)

resource aplicacion 'Microsoft.Web/sites@2023-12-01' existing = {
  name: nombreApp
}

resource cuentaFrontend 'Microsoft.Storage/storageAccounts@2023-05-01' existing = if (!empty(nombreCuentaFrontend)) {
  name: nombreCuentaFrontend
}

resource desarrolloSobreLaApi 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (hayDesarrollo) {
  scope: aplicacion
  name: guid(aplicacion.id, grupos.desarrollo, roles.websiteContributor)
  properties: {
    principalId: grupos.desarrollo
    principalType: 'Group'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.websiteContributor)
  }
}

resource desarrolloSobreElFrontend 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (hayDesarrollo && !empty(nombreCuentaFrontend)) {
  scope: cuentaFrontend
  name: guid(cuentaFrontend.id, grupos.desarrollo, roles.storageBlobDataContributor)
  properties: {
    principalId: grupos.desarrollo
    principalType: 'Group'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataContributor)
  }
}
