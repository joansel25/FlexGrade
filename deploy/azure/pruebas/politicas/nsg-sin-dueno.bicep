// PRUEBA NEGATIVA: falta la etiqueta `Dueno`. La regla «Require a tag on resources» la RECHAZA.

param centroCosto string
param ubicacion string = resourceGroup().location

resource nsg 'Microsoft.Network/networkSecurityGroups@2023-09-01' = {
  name: 'prueba-sin-dueno'
  location: ubicacion
  tags: {
    Proyecto: 'FlexGrade'
    Ambiente: 'dev'
    CentroCosto: centroCosto
  }
}
