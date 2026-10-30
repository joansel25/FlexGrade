// PRUEBA NEGATIVA: PostgreSQL con acceso público. La regla «Public network access should be
// disabled for PostgreSQL flexible servers» la RECHAZA. Usa la API 2024-08-01 porque en la
// 2022-12-01 `publicNetworkAccess` es de solo lectura y no se puede pedir.
//
// NUNCA SE DESPLIEGA: solo se valida. Desplegarla crearía un servidor de pago abierto a internet.
// `probar-politicas.sh` se niega a lanzarla si la gobernanza no está en modo `enforce`.

param dueno string
param centroCosto string
param ubicacion string = resourceGroup().location

@secure()
@description('Contraseña de un solo uso que genera el script. El servidor no llega a existir.')
param claveDePrueba string

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: 'prueba-publico-${uniqueString(resourceGroup().id)}'
  location: ubicacion
  tags: {
    Proyecto: 'FlexGrade'
    Dueno: dueno
    Ambiente: 'dev'
    CentroCosto: centroCosto
  }
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '16'
    administratorLogin: 'prueba'
    administratorLoginPassword: claveDePrueba
    storage: {
      storageSizeGB: 32
    }
    network: {
      publicNetworkAccess: 'Enabled'
    }
  }
}
