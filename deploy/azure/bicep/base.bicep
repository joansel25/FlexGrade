/*
  El grupo PERSISTENTE: registro de imágenes y almacén de secretos.

  Se despliega UNA VEZ y no se vuelve a tocar. Cuesta unos 5 USD al mes y es el precio de que
  destruir y recrear el resto sea fiable.

  POR QUÉ ESTOS DOS RECURSOS VIVEN FUERA DEL GRUPO EFÍMERO

  **El Key Vault tiene borrado lógico de 90 días y no se puede desactivar.** Si se destruyera con
  el resto, su nombre quedaría reservado y el SEGUNDO despliegue fallaría con «name already in
  use», sin mencionar en ningún momento que el recurso está en la papelera. Es exactamente el
  fallo que hace que un montaje funcione una vez y a la siguiente no, y que cuesta media hora
  entender la primera vez que se ve.

  **El ACR guarda las imágenes.** Si se borrara, cada sesión de pruebas empezaría reconstruyendo
  y volviendo a subir la imagen antes de que el App Service pudiera arrancar siquiera.

  Se despliega así, sobre su propio grupo:

    az group create --name matricula-base --location centralus
    az deployment group create --resource-group matricula-base --template-file base.bicep
*/

targetScope = 'resourceGroup'

@description('Región. La misma que el grupo efímero, para que el App Service no cruce regiones al descargar la imagen.')
param ubicacion string = resourceGroup().location

@description('Prefijo de los nombres.')
param prefijo string = 'matricula'

// Los nombres del ACR y del Key Vault son únicos en todo Azure. El sufijo sale del grupo de
// recursos: mientras el grupo sea el mismo, los nombres no cambian.
var sufijo = take(uniqueString(resourceGroup().id), 6)

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  // El nombre del ACR solo admite letras y números: sin guiones, al contrario que el resto.
  name: '${prefijo}acr${sufijo}'
  location: ubicacion
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

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: '${prefijo}-kv-${sufijo}'
  location: ubicacion
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    // POLÍTICAS DE ACCESO Y NO RBAC, a propósito. El modelo RBAC es el moderno, pero conceder un
    // rol exige permiso para escribir asignaciones de rol —Owner o User Access Administrator—,
    // que no toda suscripción de estudiante tiene. Con políticas de acceso basta con ser dueño
    // del propio almacén. En un proyecto académico, que el despliegue no dependa de un permiso
    // que quizá no existe vale más que usar el modelo más nuevo.
    enableRbacAuthorization: false
    accessPolicies: []
    // 90 días es el mínimo y no se puede bajar. Está aquí para que quede claro por qué el
    // almacén no puede vivir en el grupo efímero.
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    // La protección contra purga se deja APAGADA: con ella activada, un almacén borrado no se
    // puede eliminar de verdad ni con permisos de administrador, y en un proyecto que se
    // desmonta al acabar el semestre eso es un recurso zombi durante tres meses.
    enablePurgeProtection: null
    publicNetworkAccess: 'Enabled'
  }
}

output acrNombre string = acr.name
output acrLoginServer string = acr.properties.loginServer
output keyVaultNombre string = keyVault.name
output keyVaultUri string = keyVault.properties.vaultUri

// Recordatorio del único secreto que NO escribe Bicep. Ver el README.
output recordatorio string = 'Falta crear a mano el secreto `jwt-secret` en ${keyVault.name}. Ver README.'
