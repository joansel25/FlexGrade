// Los diagnósticos de los recursos EFÍMEROS hacia el workspace PERSISTENTE (11.1, 11.2).
//
// Se recrean en cada sesión con los recursos que vigilan. El workspace no: vive en el grupo base,
// así que la historia se acumula aunque la infraestructura vaya y venga.
//
// `categoryGroup` EN VEZ DE CATEGORÍAS SUELTAS. `allLogs` toma todas las que el recurso exponga
// hoy y las que añada mañana; escribirlas a mano deja fuera en silencio la primera categoría
// nueva. El precio es ingerir algo más: el workspace tiene un tope de 1 GB/día.
//
// LAS MÉTRICAS VAN AL WORKSPACE A PROPÓSITO. Azure Monitor ya las guarda por su cuenta, pero las
// alertas 1 y 3 son alertas de LOGS sobre la tabla `AzureMetrics`: es la única forma de contar
// periodos consecutivos (10 minutos sostenidos, tres fallos seguidos), que una alerta de métricas
// con umbral estático no admite. Sin `AllMetrics` en el plan y en el gateway, esas dos alertas no
// verían nada.

@description('Identificador del área de trabajo de Log Analytics. Vive en el grupo persistente.')
param registrosId string

@description('Nombre del App Service de la API.')
param nombreApp string

@description('Nombre del plan de App Service. Lo necesita la alerta 1 (CPU).')
param nombrePlan string

@description('Nombre del servidor de PostgreSQL.')
param nombrePostgres string

@description('Nombre del Application Gateway. Vacío si el perfil no lo despliega.')
param nombreGateway string = ''

var todosLosLogs = [
  {
    categoryGroup: 'allLogs'
    enabled: true
  }
]

var todasLasMetricas = [
  {
    category: 'AllMetrics'
    enabled: true
  }
]

resource aplicacion 'Microsoft.Web/sites@2023-12-01' existing = {
  name: nombreApp
}

resource plan 'Microsoft.Web/serverfarms@2023-12-01' existing = {
  name: nombrePlan
}

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2022-12-01' existing = {
  name: nombrePostgres
}

resource gateway 'Microsoft.Network/applicationGateways@2023-09-01' existing = if (!empty(nombreGateway)) {
  name: nombreGateway
}

// La API. `allLogs` incluye las tres categorías que importan: `AppServiceConsoleLogs` —la salida
// JSON del contenedor, donde está la auditoría académica—, `AppServiceHTTPLogs` —una línea por
// petición con su código, que leen las alertas 2 y 6— y `AppServicePlatformLogs` —arranques y
// reinicios, donde se ve si una instancia del autoescalado no llegó a levantar—.
resource diagnosticoApp 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'a-log-analytics'
  scope: aplicacion
  properties: {
    workspaceId: registrosId
    logs: todosLosLogs
    metrics: todasLasMetricas
  }
}

// El plan no tiene logs: solo métricas. De aquí sale `CpuPercentage` para la alerta 1.
resource diagnosticoPlan 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'a-log-analytics'
  scope: plan
  properties: {
    workspaceId: registrosId
    metrics: todasLasMetricas
  }
}

resource diagnosticoPostgres 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'a-log-analytics'
  scope: postgres
  properties: {
    workspaceId: registrosId
    logs: todosLosLogs
    metrics: todasLasMetricas
  }
}

// El cortafuegos de aplicación. Solo existe en el perfil de demostración, de ahí la condición.
//
// El registro del WAF es lo que convierte su demostración en algo comprobable: sin él, un intento
// de inyección bloqueado es un 403 en la pantalla y nada más. Las métricas aportan
// `UnhealthyHostCount`, que es la alerta 3.
resource diagnosticoGateway 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (!empty(nombreGateway)) {
  name: 'a-log-analytics'
  scope: gateway
  properties: {
    workspaceId: registrosId
    logs: todosLosLogs
    metrics: todasLasMetricas
  }
}

// Redis y el Storage del frontend NO tienen diagnóstico, a propósito: el primero guarda caché y
// contadores que se pueden perder sin consecuencias, y el segundo sirve archivos públicos. Ninguna
// alerta ni consulta del documento los lee, y su ingesta se pagaría contra el tope diario.
output registraGateway bool = !empty(nombreGateway)
