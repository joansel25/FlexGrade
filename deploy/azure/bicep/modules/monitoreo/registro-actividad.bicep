// Exporta el Registro de actividad de la suscripción al workspace persistente (11.1, 11.3).
//
// Sin esto la consulta de auditoría de 11.3 sobre `AzureActivity` no devuelve nada: el registro
// de actividad vive en la suscripción, no en ningún recurso, y no llega al workspace por su
// cuenta. Lo que sí funciona sin él es la alerta 5, que lee el registro directamente.

targetScope = 'subscription'

@description('Identificador del workspace persistente.')
param registrosId string

resource exportacion 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  // Azure admite como mucho cinco exportaciones por suscripción; el nombre identifica la del
  // proyecto entre ellas.
  name: 'flexgrade-registro-actividad'
  properties: {
    workspaceId: registrosId
    // Las cuatro que pide 11.1. Administrative es quién cambió qué; Security, los avisos de
    // Defender; Policy, las evaluaciones de gobernanza; Autoscale, cada decisión del
    // autoescalado, que es la evidencia de la sección 5.
    logs: [
      {
        category: 'Administrative'
        enabled: true
      }
      {
        category: 'Security'
        enabled: true
      }
      {
        category: 'Policy'
        enabled: true
      }
      {
        category: 'Autoscale'
        enabled: true
      }
    ]
  }
}
