// PRUEBA NEGATIVA: `Ambiente` fuera de dev | demo | compartido. La regla personalizada de valores
// válidos la RECHAZA.

param dueno string
param centroCosto string
param ubicacion string = resourceGroup().location

resource nsg 'Microsoft.Network/networkSecurityGroups@2023-09-01' = {
  name: 'prueba-ambiente-invalido'
  location: ubicacion
  tags: {
    Proyecto: 'FlexGrade'
    Dueno: dueno
    Ambiente: 'produccion'
    CentroCosto: centroCosto
  }
}
