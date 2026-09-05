/*
  Los permisos que la identidad de la aplicación necesita sobre el grupo PERSISTENTE.

  Se despliega con `scope: resourceGroup(grupoBase)` porque tanto el Key Vault como el ACR viven
  allí, y una asignación de permisos se hace siempre en el ámbito del recurso que se protege.

  SON DOS Y NINGUNO SOBRA

  - **Leer secretos del Key Vault.** Sin esto, las referencias `@Microsoft.KeyVault(...)` de la
    configuración no se resuelven y la aplicación recibe la cadena literal como valor de
    `DATABASE_URL`. Falla al conectarse con un error que no menciona el almacén.
  - **Descargar del ACR (`AcrPull`).** Sin esto, el App Service no puede bajar la imagen y el
    sitio se queda en «Application Error» sin haber ejecutado una sola línea.

  POR QUÉ UNO ES POLÍTICA DE ACCESO Y EL OTRO ES UN ROL

  El Key Vault se creó con políticas de acceso —ver `base.bicep`—, que solo exigen ser dueño del
  almacén. El ACR no tiene ese modelo: la única forma de conceder la descarga es una asignación
  de rol, que **requiere permiso de Owner o de User Access Administrator sobre la suscripción**.

  Si el despliegue falla aquí con `AuthorizationFailed`, esa es la causa. La salida es habilitar
  el usuario administrador del ACR y pasar sus credenciales por configuración, con el coste de
  dejar una contraseña de registro escrita donde la lee cualquiera con permiso de lectura.
*/

targetScope = 'resourceGroup'

@description('Nombre del Key Vault persistente.')
param nombreKeyVault string

@description('Nombre del ACR persistente.')
param nombreAcr string

@description('Identificador del principal de la identidad administrada de la aplicación.')
param principalId string

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: nombreKeyVault
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: nombreAcr
}

// `add` y no `replace`: reemplazar borraría las políticas de las demás identidades, incluida la
// de la persona que creó el almacén, que se quedaría sin poder leer sus propios secretos.
resource politicaDeAcceso 'Microsoft.KeyVault/vaults/accessPolicies@2023-07-01' = {
  parent: keyVault
  name: 'add'
  properties: {
    accessPolicies: [
      {
        tenantId: subscription().tenantId
        objectId: principalId
        permissions: {
          // Solo lectura, y solo de secretos. La aplicación nunca escribe en el almacén ni
          // necesita ver claves ni certificados.
          secrets: ['get', 'list']
        }
      }
    ]
  }
}

// El identificador del rol `AcrPull`, que es fijo en todo Azure.
var rolAcrPull = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource permisoDeDescarga 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: acr
  // El nombre de una asignación de rol es un GUID y tiene que ser DETERMINISTA: si cambiara
  // entre despliegues, cada uno crearía una asignación nueva y se acumularían sin límite.
  // Derivándolo del ACR, la identidad y el rol, repetir el despliegue no duplica nada.
  name: guid(acr.id, principalId, rolAcrPull)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', rolAcrPull)
    principalId: principalId
    // Sin esto, Azure intenta averiguar el tipo del principal consultando Entra ID, y falla
    // cuando la identidad se acaba de crear y todavía no se ha replicado.
    principalType: 'ServicePrincipal'
  }
}

output politicaId string = politicaDeAcceso.id
output rolId string = permisoDeDescarga.id
