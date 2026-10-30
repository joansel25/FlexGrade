// PRUEBA POSITIVA: las cuatro etiquetas con valores válidos. Tiene que VALIDAR.

param dueno string
param centroCosto string
param ubicacion string = resourceGroup().location

resource nsg 'Microsoft.Network/networkSecurityGroups@2023-09-01' = {
  name: 'prueba-conforme'
  location: ubicacion
  tags: {
    Proyecto: 'FlexGrade'
    Dueno: dueno
    Ambiente: 'dev'
    CentroCosto: centroCosto
  }
}
