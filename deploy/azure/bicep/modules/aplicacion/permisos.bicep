// Los permisos de las IDENTIDADES ADMINISTRADAS sobre el grupo persistente: leer secretos y
// descargar la imagen. Los perfiles humanos (10.1) van aparte, en `modules/acceso/`.

targetScope = 'resourceGroup'

@description('Nombre del Key Vault persistente.')
param nombreKeyVault string

@description('Nombre del ACR persistente.')
param nombreAcr string

@description('Identificador del principal de la identidad administrada de la aplicación.')
param principalId string

@description('Principal de la identidad de las tareas de un solo uso. Solo necesita descargar del ACR: no lee secretos.')
param principalTareas string = ''

import { roles } from '../comun/roles.bicep'

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: nombreKeyVault
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: nombreAcr
}

// UN SOLO ROL, Y SOLO SOBRE ESTE ALMACÉN (10.1). «Key Vault Secrets User» lee secretos y nada
// más: ni escribe, ni ve claves ni certificados.
//
// Sustituye a la política de acceso con `add` de la versión anterior, que tenía un defecto
// serio: `base.bicep` declaraba las políticas como LISTA, así que redesplegarlo las reemplazaba y
// borraba esta. Con RBAC cada permiso es un recurso independiente, y redesplegar el almacén ya no
// toca las asignaciones.
resource lecturaDeSecretos 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: keyVault
  // El nombre de una asignación de rol es un GUID y tiene que ser DETERMINISTA: si cambiara
  // entre despliegues, cada uno crearía una asignación nueva y se acumularían sin límite.
  name: guid(keyVault.id, principalId, roles.keyVaultSecretsUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.keyVaultSecretsUser)
    principalId: principalId
    // Sin esto, Azure intenta averiguar el tipo del principal consultando Entra ID, y falla
    // cuando la identidad se acaba de crear y todavía no se ha replicado.
    principalType: 'ServicePrincipal'
  }
}

resource permisoDeDescarga 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: acr
  name: guid(acr.id, principalId, roles.acrPull)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPull)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// La identidad de las tareas solo descarga la imagen. NO se le da acceso al Key Vault: la
// cadena de conexión le llega como variable de entorno segura, y un permiso que no se usa es un
// permiso que sobra.
resource permisoDeDescargaTareas 'Microsoft.Authorization/roleAssignments@2022-04-01' =
  if (!empty(principalTareas)) {
    scope: acr
    name: guid(acr.id, principalTareas, roles.acrPull)
    properties: {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPull)
      principalId: principalTareas
      principalType: 'ServicePrincipal'
    }
  }

output lecturaDeSecretosId string = lecturaDeSecretos.id
output rolId string = permisoDeDescarga.id
