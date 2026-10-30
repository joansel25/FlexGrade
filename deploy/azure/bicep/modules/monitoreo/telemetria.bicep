// Application Insights y la retención por tabla del workspace (11.1, 11.2). Grupo persistente.
//
// NO CREA OTRO WORKSPACE (11.1): Application Insights se apoya en el que ya existe, así que la
// telemetría de la API y los registros de la plataforma quedan en el mismo sitio y se cruzan en
// una sola consulta.

@description('Región.')
param ubicacion string

@description('Etiquetas comunes de la sección 12.2.')
param tags object

@description('Nombre del componente de Application Insights.')
param nombreAppInsights string

@description('Nombre del workspace de Log Analytics, en este mismo grupo.')
param nombreRegistros string

@description('Días de retención de la auditoría crítica (11.2). Pendiente de validar en coste y soporte (14).')
@minValue(30)
@maxValue(730)
param retencionAuditoriaDias int

resource registros 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: nombreRegistros
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: nombreAppInsights
  location: ubicacion
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: registros.id
    // Solo ingesta por el workspace: el modo clásico, con almacenamiento propio, está retirado.
    IngestionMode: 'LogAnalytics'
  }
}

// LA RETENCIÓN POR TABLA (11.2)
//
// La general del workspace es de 30 días (`base.bicep`). Estas dos tablas guardan 90 porque son
// la auditoría:
//
//   AzureActivity           quién cambió qué en Azure. Ya trae 90 de serie y Azure no lo cobra;
//                           se declara para que el valor no dependa de un defecto de la plataforma.
//   AppServiceConsoleLogs   la salida JSON del backend, donde HOY está la auditoría académica de
//                           las matrículas. El documento nombra `AppTraces` (Parte A); esa tabla
//                           solo se llena cuando la API se instrumente con Application Insights, y
//                           entonces es la que hay que añadir aquí.
//
// `totalRetentionInDays` igual a la interactiva: sin archivo a largo plazo, que es otro precio.
var tablasDeAuditoria = [
  'AzureActivity'
  'AppServiceConsoleLogs'
]

resource retencion 'Microsoft.OperationalInsights/workspaces/tables@2022-10-01' = [
  for tabla in tablasDeAuditoria: {
    parent: registros
    name: tabla
    properties: {
      retentionInDays: retencionAuditoriaDias
      totalRetentionInDays: retencionAuditoriaDias
    }
  }
]

output appInsightsId string = appInsights.id
